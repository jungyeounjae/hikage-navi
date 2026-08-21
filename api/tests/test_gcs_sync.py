from pathlib import Path

import pytest

from hikage_navi.gcs_sync import (
    local_ready,
    parse_gcs_uri,
    read_stamp,
    should_skip_sync,
    stamp_path,
    sync_enabled,
    write_stamp,
)


def test_parse_gcs_uri():
    assert parse_gcs_uri("gs://hikage-navi-data/processed/tokyo23") == (
        "hikage-navi-data",
        "processed/tokyo23",
    )
    assert parse_gcs_uri("gs://b/p/q/") == ("b", "p/q")


def test_parse_gcs_uri_rejects_bad():
    with pytest.raises(ValueError):
        parse_gcs_uri("https://example.com/x")
    with pytest.raises(ValueError):
        parse_gcs_uri("gs://bucket-only")


def test_sync_enabled_defaults_true(monkeypatch):
    monkeypatch.delenv("HIKAGE_GCS_SYNC", raising=False)
    assert sync_enabled() is True
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "0")
    assert sync_enabled() is False
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "false")
    assert sync_enabled() is False


def test_stamp_roundtrip(tmp_path: Path):
    write_stamp(tmp_path, "12345")
    assert stamp_path(tmp_path).name == ".gcs-sync-stamp"
    assert read_stamp(tmp_path) == "12345"


def test_should_skip_requires_ready_and_matching_stamp(tmp_path: Path):
    assert should_skip_sync(tmp_path, "9") is False
    (tmp_path / "walk-graph.json").write_text("{}", encoding="utf-8")
    (tmp_path / "boundary.geojson").write_text("{}", encoding="utf-8")
    assert local_ready(tmp_path) is True
    assert should_skip_sync(tmp_path, "9") is False
    write_stamp(tmp_path, "9")
    assert should_skip_sync(tmp_path, "9") is True
    assert should_skip_sync(tmp_path, "10") is False
