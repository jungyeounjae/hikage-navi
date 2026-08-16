#!/usr/bin/env python3
"""시부야구 PLATEAU·OSM 전처리 → data/processed/

실행:
  cd api && . .venv/bin/activate && pip install -e ".[preprocess]"
  python scripts/preprocess.py

환경변수:
  HIKAGE_ROOT — 저장소 루트 (기본: 이 파일 기준 ../../)
  HIKAGE_USE_PBF=1 — Geofabrik kanto PBF + pyrosm (선택)
  HIKAGE_CITYGML_URL — PLATEAU CityGML zip URL

공개 OSRM/Nominatim 경로 서버는 쓰지 않는다.
경계 geocode 1회, 보행망은 Overpass(폴리곤) 또는 로컬 PBF.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

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

NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "bldg": "http://www.opengis.net/citygml/building/2.0",
    "core": "http://www.opengis.net/citygml/2.0",
}


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


def build_boundary():
    import geopandas as gpd
    import osmnx as ox

    print("1/4 시부야 경계 (Nominatim geocode 1회)…")
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx_cache")
    gdf = ox.geocode_to_gdf("Shibuya, Tokyo, Japan")
    gdf = gdf.to_crs(epsg=4326)
    geom = gdf.geometry.union_all() if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    out = PROCESSED / "shibuya-boundary.geojson"
    feature = {
        "type": "Feature",
        "properties": {"name": "Shibuya"},
        "geometry": json.loads(gpd.GeoSeries([geom], crs="EPSG:4326").to_json())[
            "features"
        ][0]["geometry"],
    }
    out.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out}")
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


def build_buildings(boundary_geom) -> None:
    from shapely.geometry import Polygon, mapping
    from shapely.prepared import prep

    print("2/4 PLATEAU 건물 (CityGML zip)…")
    _download(CITYGML_URL, CITYGML_ZIP)
    extract_dir = RAW / "citygml_shibuya"
    if not extract_dir.exists():
        print("  zip 압축 해제…")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(CITYGML_ZIP) as zf:
            zf.extractall(extract_dir)

    bldg_files = sorted(extract_dir.rglob("*_bldg_*.gml"))
    if not bldg_files:
        bldg_files = sorted(extract_dir.rglob("*bldg*.gml"))
    print(f"  CityGML 건물 파일 {len(bldg_files)}개")

    prepared = prep(boundary_geom)
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

    out = PROCESSED / "shibuya-buildings.geojson"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {out} ({len(features)} buildings)")
    if len(features) < 1000:
        print("  경고: 건물 수 < 1000", file=sys.stderr)


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


def build_walk_graph(boundary_geom) -> None:
    import osmnx as ox

    print("3/4 보행 그래프…")
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx_cache")
    out = PROCESSED / "shibuya-walk-graph.json"

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
        _graph_to_walk_json(G, out)
        return

    print("  osmnx.graph_from_polygon (Overpass, 시부야 폴리곤만)…")
    print("  ※ 전체 Kanto PBF가 필요하면 HIKAGE_USE_PBF=1 로 재실행")
    G = ox.graph_from_polygon(boundary_geom, network_type="walk", simplify=True)
    _graph_to_walk_json(G, out)


def main() -> None:
    ensure_dirs()
    boundary = build_boundary()
    build_buildings(boundary)
    build_walk_graph(boundary)
    print("4/4 완료:", PROCESSED)


if __name__ == "__main__":
    main()
