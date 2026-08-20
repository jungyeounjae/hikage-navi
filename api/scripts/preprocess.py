#!/usr/bin/env python3
"""시부야 / 東京23区 PLATEAU·OSM 전처리 → data/processed/

실행:
  cd api && . .venv/bin/activate && pip install -e ".[preprocess]"
  python scripts/preprocess.py                  # 기존 시부야 단독 산출
  python scripts/preprocess.py --wards 13113    # tokyo23 레이아웃 (시부야만)
  python scripts/preprocess.py --wards all      # 23구 전부

환경변수:
  HIKAGE_ROOT — 저장소 루트 (기본: 이 파일 기준 ../../)
  HIKAGE_USE_PBF=1 — Geofabrik kanto PBF + pyrosm (선택)
  HIKAGE_CITYGML_URL — 시부야 단독 모드 PLATEAU CityGML zip URL
  HIKAGE_WATER_ONLY=1 — 기존 경계만 읽고 OSM 급수 스팟만 추출

공개 OSRM/Nominatim 경로 서버는 쓰지 않는다.
경계 geocode 1회(구별), 보행망은 Overpass(폴리곤) 또는 로컬 PBF.

tokyo23 산출 레이아웃:
  data/processed/tokyo23/
    boundary.geojson
    walk-graph.json
    wards/{code}/buildings.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from hikage_navi.wards import TOKYO_23_WARD_CODES
except ImportError:  # editable 미설치·병합 전 최소 폴백
    TOKYO_23_WARD_CODES = [f"{c}" for c in range(13101, 13124)]

ROOT = Path(os.environ.get("HIKAGE_ROOT", Path(__file__).resolve().parents[2]))
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PBF_URL = "https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf"
PBF_PATH = RAW / "kanto-latest.osm.pbf"
CITYGML_URL = os.environ.get(
    "HIKAGE_CITYGML_URL",
    "https://assets.cms.plateau.reearth.io/assets/48/e684f3-fb86-44d4-b7e3-a3d72d54582d/13113_shibuya-ku_pref_2025_citygml_1_op.zip",
)
CITYGML_ZIP = RAW / "13113_shibuya-ku_pref_2025_citygml_1_op.zip"
USE_PBF = os.environ.get("HIKAGE_USE_PBF", "").strip() in {"1", "true", "yes"}
WATER_ONLY = os.environ.get("HIKAGE_WATER_ONLY", "").strip() in {"1", "true", "yes"}
WATER_TAGS = {"amenity": "drinking_water", "drinking_water": "yes"}

# PLATEAU 2025 CityGML (CMS). 13113은 기존 시부야 파이프라인과 동일 URL 유지.
PLATEAU_CITYGML_URLS: dict[str, str] = {
    "13101": "https://assets.cms.plateau.reearth.io/assets/5d/dc07c5-ace7-465a-9c99-53f6d78f6164/13101_chiyoda-ku_pref_2025_citygml_1_op.zip",
    "13102": "https://assets.cms.plateau.reearth.io/assets/93/1f058b-e06b-445c-ae62-2e02cdf72849/13102_chuo-ku_pref_2025_citygml_1_op.zip",
    "13103": "https://assets.cms.plateau.reearth.io/assets/ea/d75459-6d62-4a1f-8081-317603bd5f8d/13103_minato-ku_pref_2025_citygml_1_op.zip",
    "13104": "https://assets.cms.plateau.reearth.io/assets/84/48ebed-93d8-4196-bdda-e1db9590d3d1/13104_shinjuku-ku_pref_2025_citygml_1_op.zip",
    "13105": "https://assets.cms.plateau.reearth.io/assets/4b/ac4a9f-1bdf-4978-bbfa-8ba8a80d12a0/13105_bunkyo-ku_pref_2025_citygml_1_op.zip",
    "13106": "https://assets.cms.plateau.reearth.io/assets/80/45b2b1-5a88-40ab-9877-70b540b8707e/13106_taito-ku_city_2025_citygml_1_op.zip",
    "13107": "https://assets.cms.plateau.reearth.io/assets/af/d16ede-837d-458a-af51-16771bbb96d8/13107_sumida-ku_pref_2025_citygml_1_op.zip",
    "13108": "https://assets.cms.plateau.reearth.io/assets/55/c134fe-ccfb-4c1b-9054-d8c6f44b7597/13108_koto-ku_pref_2025_citygml_1_op.zip",
    "13109": "https://assets.cms.plateau.reearth.io/assets/4b/90d7b7-679a-46d4-a842-7706fec36d40/13109_shinagawa-ku_pref_2025_citygml_1_op.zip",
    "13110": "https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op.zip",
    "13111": "https://assets.cms.plateau.reearth.io/assets/2c/6a2f27-a1e1-466a-a8cf-4627060f7ca4/13111_ota-ku_pref_2025_citygml_1_op.zip",
    "13112": "https://assets.cms.plateau.reearth.io/assets/b4/38c131-2e1e-4226-95f7-44f2b12debd7/13112_setagaya-ku_pref_2025_citygml_1_op.zip",
    "13113": "https://assets.cms.plateau.reearth.io/assets/48/e684f3-fb86-44d4-b7e3-a3d72d54582d/13113_shibuya-ku_pref_2025_citygml_1_op.zip",
    "13114": "https://assets.cms.plateau.reearth.io/assets/89/a1621d-b7db-4499-a3c2-673109be0704/13114_nakano-ku_pref_2025_citygml_1_op.zip",
    "13115": "https://assets.cms.plateau.reearth.io/assets/1f/4afed5-f8d0-42e7-b334-e507471ecd51/13115_suginami-ku_pref_2025_citygml_1_op.zip",
    "13116": "https://assets.cms.plateau.reearth.io/assets/cc/d90677-ae87-4718-8899-f6131004cfa5/13116_toshima-ku_pref_2025_citygml_1_op.zip",
    "13117": "https://assets.cms.plateau.reearth.io/assets/01/9a60eb-4cd2-4bfe-907e-1338e0eacd8e/13117_kita-ku_pref_2025_citygml_1_op.zip",
    "13118": "https://assets.cms.plateau.reearth.io/assets/a1/351cc4-8dfa-4825-b22f-a55a7fe09125/13118_arakawa-ku_pref_2025_citygml_1_op.zip",
    "13119": "https://assets.cms.plateau.reearth.io/assets/26/859c29-8352-4339-b764-8e6eb42e9eeb/13119_itabashi-ku_pref_2025_citygml_1_op.zip",
    "13120": "https://assets.cms.plateau.reearth.io/assets/24/f0d0d7-c47a-4647-95f4-fd969c878bcf/13120_nerima-ku_pref_2025_citygml_1_op.zip",
    "13121": "https://assets.cms.plateau.reearth.io/assets/77/d608e2-b588-4ff4-997b-da1bf308d434/13121_adachi-ku_pref_2025_citygml_1_op.zip",
    "13122": "https://assets.cms.plateau.reearth.io/assets/61/f4c5b8-5d12-4093-903f-75d7132ce97d/13122_katsushika-ku_pref_2025_citygml_1_op.zip",
    "13123": "https://assets.cms.plateau.reearth.io/assets/e6/75f5f9-3352-4d80-a79c-3a2421f75d5a/13123_edogawa-ku_pref_2025_citygml_1_op.zip",
}

WARD_GEOCODE_QUERIES: dict[str, str] = {
    "13101": "千代田区, 東京都, 日本",
    "13102": "中央区, 東京都, 日本",
    "13103": "港区, 東京都, 日本",
    "13104": "新宿区, 東京都, 日本",
    "13105": "文京区, 東京都, 日本",
    "13106": "台東区, 東京都, 日本",
    "13107": "墨田区, 東京都, 日本",
    "13108": "江東区, 東京都, 日本",
    "13109": "品川区, 東京都, 日本",
    "13110": "目黒区, 東京都, 日本",
    "13111": "大田区, 東京都, 日本",
    "13112": "世田谷区, 東京都, 日本",
    "13113": "渋谷区, 東京都, 日本",
    "13114": "中野区, 東京都, 日本",
    "13115": "杉並区, 東京都, 日本",
    "13116": "豊島区, 東京都, 日本",
    "13117": "北区, 東京都, 日本",
    "13118": "荒川区, 東京都, 日本",
    "13119": "板橋区, 東京都, 日本",
    "13120": "練馬区, 東京都, 日本",
    "13121": "足立区, 東京都, 日本",
    "13122": "葛飾区, 東京都, 日本",
    "13123": "江戸川区, 東京都, 日本",
}

NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "bldg": "http://www.opengis.net/citygml/building/2.0",
    "core": "http://www.opengis.net/citygml/2.0",
}


def parse_wards_arg(raw: str) -> list[str]:
    """`--wards all` 또는 콤마 구분 구 코드 → 코드 리스트."""
    text = raw.strip()
    if text.lower() == "all":
        return list(TOKYO_23_WARD_CODES)
    codes = [c.strip() for c in text.split(",") if c.strip()]
    if not codes:
        raise SystemExit("--wards 값이 비어 있습니다 (예: 13113 또는 all)")
    allowed = set(TOKYO_23_WARD_CODES)
    bad = [c for c in codes if c not in allowed]
    if bad:
        raise SystemExit(
            f"알 수 없는 구 코드: {', '.join(bad)} "
            f"(허용: {TOKYO_23_WARD_CODES[0]}–{TOKYO_23_WARD_CODES[-1]} 또는 all)"
        )
    # 순서 유지, 중복 제거
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def citygml_url_for_ward(code: str) -> str:
    url = PLATEAU_CITYGML_URLS.get(code)
    if not url:
        raise SystemExit(
            f"구 코드 {code} 에 대한 PLATEAU CityGML URL이 등록되어 있지 않습니다. "
            "PLATEAU_CITYGML_URLS 를 갱신하세요."
        )
    return url


def tokyo23_output_paths(ward_codes: list[str]) -> dict:
    root = PROCESSED / "tokyo23"
    return {
        "root": root,
        "boundary": root / "boundary.geojson",
        "walk_graph": root / "walk-graph.json",
        "wards": {
            code: root / "wards" / code / "buildings.geojson" for code in ward_codes
        },
    }


def ensure_tokyo23_dirs(paths: dict) -> None:
    paths["root"].mkdir(parents=True, exist_ok=True)
    for out in paths["wards"].values():
        out.parent.mkdir(parents=True, exist_ok=True)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="시부야 또는 東京23区 PLATEAU·OSM 전처리",
    )
    p.add_argument(
        "--wards",
        metavar="CODES",
        default=None,
        help="tokyo23 모드: 구 코드(콤마) 또는 all. 생략 시 기존 시부야 단독 산출.",
    )
    return p


def ensure_dirs() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"  이미 있음: {dest} ({dest.stat().st_size // 1_000_000} MB)")
        return
    print(f"  다운로드: {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")

    def _reporthook(block_num, block_size, total_size):
        if total_size <= 0:
            return
        done = block_num * block_size
        pct = min(100, done * 100 // total_size)
        if block_num % 500 == 0:
            print(f"    {pct}% ({done // 1_000_000} MB)", flush=True)

    urllib.request.urlretrieve(url, tmp, _reporthook)
    tmp.replace(dest)
    print(f"  저장: {dest} ({dest.stat().st_size // 1_000_000} MB)")


def _geocode_polygon(query: str):
    import geopandas as gpd
    import osmnx as ox

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx_cache")
    gdf = ox.geocode_to_gdf(query)
    gdf = gdf.to_crs(epsg=4326)
    geom = gdf.geometry.union_all() if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    return geom


def _write_boundary_feature(geom, out: Path, name: str, properties: dict | None = None) -> None:
    import geopandas as gpd

    props = {"name": name}
    if properties:
        props.update(properties)
    feature = {
        "type": "Feature",
        "properties": props,
        "geometry": json.loads(gpd.GeoSeries([geom], crs="EPSG:4326").to_json())[
            "features"
        ][0]["geometry"],
    }
    out.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out}")


def build_boundary():
    print("1/5 시부야 경계 (Nominatim geocode 1회)…")
    geom = _geocode_polygon("Shibuya, Tokyo, Japan")
    _write_boundary_feature(geom, PROCESSED / "shibuya-boundary.geojson", "Shibuya")
    return geom


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _parse_pos_list(text: str) -> list[tuple[float, float]]:
    nums = [float(x) for x in text.split()]
    pts: list[tuple[float, float]] = []
    # gml:posList is x y [z] x y [z] …
    if len(nums) % 3 == 0:
        for i in range(0, len(nums), 3):
            pts.append((nums[i], nums[i + 1]))
    else:
        for i in range(0, len(nums), 2):
            if i + 1 < len(nums):
                pts.append((nums[i], nums[i + 1]))
    return pts


def _ring_from_polygon_el(poly_el: ET.Element) -> list[tuple[float, float]] | None:
    for pl in poly_el.iter():
        if _local_name(pl.tag) == "posList" and pl.text:
            pts = _parse_pos_list(pl.text)
            if len(pts) >= 3:
                return pts
    # fallback: sequence of gml:pos
    coords: list[tuple[float, float]] = []
    for pos in poly_el.iter():
        if _local_name(pos.tag) == "pos" and pos.text:
            nums = [float(x) for x in pos.text.split()]
            if len(nums) >= 2:
                coords.append((nums[0], nums[1]))
    return coords if len(coords) >= 3 else None


def _footprint_from_building(bldg: ET.Element) -> list[tuple[float, float]] | None:
    # Prefer lod0RoofEdge / lod0FootPrint, else first Polygon in building
    preferred = []
    other = []
    for el in bldg.iter():
        name = _local_name(el.tag)
        if name in {"lod0RoofEdge", "lod0FootPrint", "lod1TerrainIntersection"}:
            preferred.append(el)
        elif name == "Polygon":
            other.append(el)
    for container in preferred:
        for poly in container.iter():
            if _local_name(poly.tag) == "Polygon":
                ring = _ring_from_polygon_el(poly)
                if ring:
                    return ring
    for poly in other:
        ring = _ring_from_polygon_el(poly)
        if ring:
            return ring
    return None


def _height_from_building(bldg: ET.Element) -> float:
    for el in bldg.iter():
        if _local_name(el.tag) == "measuredHeight" and el.text:
            try:
                return float(el.text.strip())
            except ValueError:
                continue
    return 0.0


def _detect_crs_and_transform(pts: list[tuple[float, float]]):
    """Return lon/lat ring. PLATEAU EPSG:6697 posList is often lat,lon[,z]."""
    from pyproj import Transformer

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # Geographic lat, lon (common in PLATEAU CityGML 6697)
    if min(xs) > 20 and max(xs) < 50 and min(ys) > 120 and max(ys) < 150:
        return [(y, x) for x, y in pts]
    # Already lon, lat
    if min(xs) > 120 and max(xs) < 150 and min(ys) > 20 and max(ys) < 50:
        return [(x, y) for x, y in pts]
    # EPSG:6677 (JGD2011 / Japan Plane Rectangular CS IX)
    to_ll = Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
    out = []
    for x, y in pts:
        lon, lat = to_ll.transform(x, y)
        out.append((float(lon), float(lat)))
    return out


def _buildings_from_citygml_file(path: Path) -> list[tuple[list[tuple[float, float]], float]]:
    # Large files: iterparse
    results: list[tuple[list[tuple[float, float]], float]] = []
    context = ET.iterparse(path, events=("end",))
    for _event, elem in context:
        if _local_name(elem.tag) != "Building":
            continue
        # skip BuildingPart nested? take top-level only — BuildingPart also named Building in some files
        height = _height_from_building(elem)
        ring = _footprint_from_building(elem)
        if ring and height >= 2.0:
            try:
                lonlat = _detect_crs_and_transform(ring)
                if lonlat[0] != lonlat[-1]:
                    lonlat = lonlat + [lonlat[0]]
                results.append((lonlat, height))
            except Exception:
                pass
        elem.clear()
    return results


def _extract_buildings_clipped(zip_path: Path, extract_dir: Path, clip_geom) -> list[dict]:
    from shapely.geometry import Polygon, mapping
    from shapely.prepared import prep

    if not extract_dir.exists():
        print("  zip 압축 해제…")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

    bldg_files = sorted(extract_dir.rglob("*_bldg_*.gml"))
    if not bldg_files:
        bldg_files = sorted(extract_dir.rglob("*bldg*.gml"))
    print(f"  CityGML 건물 파일 {len(bldg_files)}개")

    prepared = prep(clip_geom)
    features = []
    for i, path in enumerate(bldg_files, start=1):
        if i % 20 == 0 or i == 1:
            print(f"    파싱 {i}/{len(bldg_files)}: {path.name}", flush=True)
        for ring, height in _buildings_from_citygml_file(path):
            try:
                poly = Polygon(ring)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty or not prepared.intersects(poly):
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"height": float(height)},
                        "geometry": mapping(poly),
                    }
                )
            except Exception:
                continue
    return features


def build_buildings(boundary_geom) -> None:
    print("2/5 PLATEAU 건물 (CityGML zip)…")
    _download(CITYGML_URL, CITYGML_ZIP)
    features = _extract_buildings_clipped(
        CITYGML_ZIP, RAW / "citygml_shibuya", boundary_geom
    )
    out = PROCESSED / "shibuya-buildings.geojson"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {out} ({len(features)} buildings)")
    if len(features) < 1000:
        print("  경고: 건물 수 < 1000", file=sys.stderr)


def build_tokyo23_buildings(ward_codes: list[str], ward_geoms: dict, paths: dict) -> None:
    print(f"  구별 CityGML ({len(ward_codes)}구)…")
    for code in ward_codes:
        url = citygml_url_for_ward(code)
        zip_name = url.rsplit("/", 1)[-1]
        zip_path = RAW / zip_name
        extract_dir = RAW / f"citygml_{code}"
        print(f"  [{code}] {zip_name}")
        _download(url, zip_path)
        features = _extract_buildings_clipped(zip_path, extract_dir, ward_geoms[code])
        out = paths["wards"][code]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
            encoding="utf-8",
        )
        max_h = max((f["properties"]["height"] for f in features), default=0.0)
        meta = {
            "bounds": list(ward_geoms[code].bounds),
            "max_height_m": max_h,
        }
        meta_path = out.parent / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        print(f"  → {out} ({len(features)} buildings)")
        if len(features) < 100:
            print(f"  경고: {code} 건물 수 < 100", file=sys.stderr)


def _graph_to_walk_json(G, out: Path) -> None:
    nodes = []
    id_map: dict = {}
    for i, (nid, data) in enumerate(G.nodes(data=True), start=1):
        id_map[nid] = i
        nodes.append(
            {
                "id": i,
                "lon": float(data["x"]),
                "lat": float(data["y"]),
            }
        )

    edges = []
    seen: set[tuple[int, int]] = set()
    for u, v, data in G.edges(data=True):
        a, b = id_map[u], id_map[v]
        key = (a, b) if a < b else (b, a)
        if key in seen:
            continue
        seen.add(key)
        if "geometry" in data and data["geometry"] is not None:
            coords = [(float(x), float(y)) for x, y in data["geometry"].coords]
        else:
            coords = [
                (float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
                (float(G.nodes[v]["x"]), float(G.nodes[v]["y"])),
            ]
        edges.append({"u": a, "v": b, "coords": coords})

    out.write_text(
        json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {out} (nodes={len(nodes)}, edges={len(edges)})")
    if len(nodes) < 1000:
        print("  경고: 노드 수 < 1000", file=sys.stderr)


def build_walk_graph(boundary_geom, out: Path | None = None, label: str = "시부야") -> None:
    import osmnx as ox

    print(f"보행 그래프 ({label})…")
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx_cache")
    dest = out if out is not None else PROCESSED / "shibuya-walk-graph.json"

    if USE_PBF:
        try:
            from pyrosm import OSM
        except ImportError as exc:
            raise SystemExit(
                "HIKAGE_USE_PBF=1 이면 pyrosm이 필요합니다: pip install pyrosm"
            ) from exc
        _download(PBF_URL, PBF_PATH)
        minx, miny, maxx, maxy = boundary_geom.bounds
        print("  pyrosm으로 PBF에서 walking 네트워크 추출…")
        osm = OSM(str(PBF_PATH), bounding_box=[minx, miny, maxx, maxy])
        nodes_gdf, edges_gdf = osm.get_network(network_type="walking", nodes=True)
        G = ox.graph_from_gdfs(nodes_gdf, edges_gdf)
        _graph_to_walk_json(G, dest)
        return

    print(f"  osmnx.graph_from_polygon (Overpass, {label} 폴리곤)…")
    print("  ※ 전체 Kanto PBF가 필요하면 HIKAGE_USE_PBF=1 로 재실행")
    G = ox.graph_from_polygon(boundary_geom, network_type="walk", simplify=True)
    _graph_to_walk_json(G, dest)


def _series_value(row, key: str):
    import pandas as pd

    if key not in row.index:
        return None
    val = row[key]
    if val is None or pd.isna(val):
        return None
    return val


def _osm_id_from_row(idx, row) -> str:
    osmid = _series_value(row, "osmid")
    if osmid is not None:
        return str(osmid)
    if isinstance(idx, tuple) and len(idx) >= 2:
        etype, oid = idx[0], idx[1]
        prefix = {"node": "n", "way": "w", "relation": "r"}.get(str(etype), "")
        return f"{prefix}{oid}"
    return str(idx)


def _point_features_from_gdf(gdf, boundary_geom) -> list[dict]:
    from shapely.geometry import mapping

    from hikage_navi.water import spot_from_properties, water_spot_feature_properties

    features: list[dict] = []
    if gdf is None or getattr(gdf, "empty", True):
        return features
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.geom_type != "Point":
            continue
        if not geom.intersects(boundary_geom):
            continue
        lon, lat = float(geom.x), float(geom.y)
        amenity = _series_value(row, "amenity")
        drinking_water = _series_value(row, "drinking_water")
        if amenity != "drinking_water" and str(drinking_water) != "yes":
            continue
        bottle = _series_value(row, "bottle")
        props = {
            "id": _osm_id_from_row(idx, row),
            "name": _series_value(row, "name"),
            "amenity": amenity,
            "drinking_water": drinking_water,
            "bottle": bottle,
            "access": _series_value(row, "access"),
            "opening_hours": _series_value(row, "opening_hours"),
        }
        spot = spot_from_properties(props, lon=lon, lat=lat)
        features.append(
            {
                "type": "Feature",
                "properties": water_spot_feature_properties(spot, bottle=bottle),
                "geometry": mapping(geom),
            }
        )
    return features


def load_boundary_geom():
    from shapely.geometry import shape

    path = PROCESSED / "shibuya-boundary.geojson"
    if not path.is_file():
        raise SystemExit(
            f"HIKAGE_WATER_ONLY=1 인데 경계 파일이 없습니다: {path}\n"
            "먼저 전체 전처리를 실행하거나 경계를 생성하세요."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("type") == "FeatureCollection":
        geom = shape(raw["features"][0]["geometry"])
    else:
        geom = shape(raw["geometry"])
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    return geom


def build_water_spots(boundary_geom, out: Path | None = None) -> None:
    import osmnx as ox

    print("OSM 급수 스팟 (Point만)…")
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx_cache")
    dest = out if out is not None else PROCESSED / "shibuya-water-spots.geojson"

    try:
        if USE_PBF:
            try:
                from pyrosm import OSM
            except ImportError as exc:
                raise SystemExit(
                    "HIKAGE_USE_PBF=1 이면 pyrosm이 필요합니다: pip install pyrosm"
                ) from exc
            _download(PBF_URL, PBF_PATH)
            minx, miny, maxx, maxy = boundary_geom.bounds
            print("  pyrosm POI 필터로 급수 추출…")
            osm = OSM(str(PBF_PATH), bounding_box=[minx, miny, maxx, maxy])
            gdf = osm.get_pois(
                custom_filter={
                    "amenity": ["drinking_water"],
                    "drinking_water": ["yes"],
                }
            )
        else:
            print("  osmnx.features_from_polygon (Overpass)…")
            gdf = ox.features_from_polygon(boundary_geom, tags=WATER_TAGS)
        features = _point_features_from_gdf(gdf, boundary_geom)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"  급수 추출 실패 (산출물 생략): {exc}", file=sys.stderr)
        return

    dest.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {dest} ({len(features)} points)")


def run_shibuya() -> None:
    boundary = build_boundary()
    build_buildings(boundary)
    build_walk_graph(boundary)
    build_water_spots(boundary)
    print("5/5 완료:", PROCESSED)


def run_tokyo23(ward_codes: list[str]) -> None:
    from shapely.ops import unary_union

    paths = tokyo23_output_paths(ward_codes)
    ensure_tokyo23_dirs(paths)

    # Validate URLs up front so missing codes fail before downloads
    for code in ward_codes:
        citygml_url_for_ward(code)

    print(f"tokyo23 전처리: {', '.join(ward_codes)}")
    print(f"1/3 경계 union ({len(ward_codes)}구, Nominatim)…")
    ward_geoms: dict = {}
    for code in ward_codes:
        query = WARD_GEOCODE_QUERIES[code]
        print(f"  geocode {code}: {query}")
        ward_geoms[code] = _geocode_polygon(query)

    union = unary_union(list(ward_geoms.values()))
    _write_boundary_feature(
        union,
        paths["boundary"],
        "Tokyo23",
        properties={"wards": ",".join(ward_codes)},
    )

    print(f"2/3 PLATEAU 건물…")
    build_tokyo23_buildings(ward_codes, ward_geoms, paths)
    print("3/4 보행 그래프…")
    build_walk_graph(union, out=paths["walk_graph"], label="tokyo23 union")
    print("4/4 급수 스팟…")
    build_water_spots(union, out=paths["root"] / "water-spots.geojson")
    print("완료:", paths["root"])


def main(argv: list[str] | None = None) -> None:
    ensure_dirs()
    args = build_arg_parser().parse_args(argv)
    if WATER_ONLY and args.wards is None:
        boundary = load_boundary_geom()
        build_water_spots(boundary)
        print("완료 (water only):", PROCESSED)
        return
    if args.wards is not None:
        run_tokyo23(parse_wards_arg(args.wards))
        return
    run_shibuya()


if __name__ == "__main__":
    main()
