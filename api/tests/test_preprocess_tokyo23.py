"""tokyo23 preprocess CLI / path scaffolding (no network downloads)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load_preprocess():
    path = SCRIPTS / "preprocess.py"
    spec = importlib.util.spec_from_file_location("hikage_preprocess", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hikage_preprocess"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def prep():
    return _load_preprocess()


def test_parse_wards_all(prep):
    assert prep.parse_wards_arg("all") == prep.TOKYO_23_WARD_CODES
    assert len(prep.parse_wards_arg("all")) == 23


def test_parse_wards_single(prep):
    assert prep.parse_wards_arg("13113") == ["13113"]


def test_parse_wards_comma(prep):
    assert prep.parse_wards_arg("13113,13101") == ["13113", "13101"]


def test_parse_wards_invalid(prep):
    with pytest.raises(SystemExit) as exc:
        prep.parse_wards_arg("99999")
    assert "99999" in str(exc.value)


def test_citygml_url_for_known_ward(prep):
    url = prep.citygml_url_for_ward("13113")
    assert "13113" in url
    assert url.endswith(".zip")


def test_citygml_url_missing_ward_names_code(prep):
    with pytest.raises(SystemExit) as exc:
        prep.citygml_url_for_ward("00000")
    assert "00000" in str(exc.value)


def test_tokyo23_output_layout(prep, tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "PROCESSED", tmp_path)
    paths = prep.tokyo23_output_paths(["13113", "13101"])
    assert paths["root"] == tmp_path / "tokyo23"
    assert paths["boundary"] == tmp_path / "tokyo23" / "boundary.geojson"
    assert paths["walk_graph"] == tmp_path / "tokyo23" / "walk-graph.json"
    assert paths["wards"]["13113"] == tmp_path / "tokyo23" / "wards" / "13113" / "buildings.geojson"
    assert paths["wards"]["13101"] == tmp_path / "tokyo23" / "wards" / "13101" / "buildings.geojson"


def test_ensure_tokyo23_dirs(prep, tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "PROCESSED", tmp_path)
    paths = prep.tokyo23_output_paths(["13113"])
    prep.ensure_tokyo23_dirs(paths)
    assert paths["root"].is_dir()
    assert (paths["root"] / "wards" / "13113").is_dir()


def test_argparse_wards_default_none(prep):
    parser = prep.build_arg_parser()
    ns = parser.parse_args([])
    assert ns.wards is None


def test_argparse_wards_all(prep):
    parser = prep.build_arg_parser()
    ns = parser.parse_args(["--wards", "all"])
    assert ns.wards == "all"


def test_plateau_url_map_covers_all_23(prep):
    for code in prep.TOKYO_23_WARD_CODES:
        assert code in prep.PLATEAU_CITYGML_URLS
        assert prep.PLATEAU_CITYGML_URLS[code]
        assert code in prep.citygml_url_for_ward(code)
