from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hikage_navi.gcs_sync import (
    download_prefix,
    local_ready,
    parse_gcs_uri,
    read_stamp,
    should_skip_sync,
    stamp_path,
    sync_enabled,
    sync_processed,
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
    assert local_ready(tmp_path) is False
    (tmp_path / "wards").mkdir()
    assert local_ready(tmp_path) is True
    assert should_skip_sync(tmp_path, "9") is False
    write_stamp(tmp_path, "9")
    assert should_skip_sync(tmp_path, "9") is True
    assert should_skip_sync(tmp_path, "10") is False


def _blob(name: str, generation: int = 1):
    b = MagicMock()
    b.name = name
    b.generation = generation
    b.download_to_filename = MagicMock()
    return b


def test_sync_processed_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "0")
    client = MagicMock()
    assert sync_processed(client=client, data_dir=tmp_path) == "disabled"
    client.bucket.assert_not_called()


def test_sync_processed_skips_when_stamp_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "1")
    (tmp_path / "walk-graph.json").write_text("{}", encoding="utf-8")
    (tmp_path / "boundary.geojson").write_text("{}", encoding="utf-8")
    (tmp_path / "wards").mkdir()
    write_stamp(tmp_path, "42")

    walk = _blob("processed/tokyo23/walk-graph.json", generation=42)
    bucket = MagicMock()
    bucket.blob.return_value = walk
    client = MagicMock()
    client.bucket.return_value = bucket

    assert sync_processed(client=client, data_dir=tmp_path) == "skipped"
    walk.download_to_filename.assert_not_called()


def test_sync_processed_downloads_when_stamp_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "1")
    prefix = "processed/tokyo23"
    walk = _blob(f"{prefix}/walk-graph.json", generation=7)
    boundary = _blob(f"{prefix}/boundary.geojson", generation=1)
    ward = _blob(f"{prefix}/wards/13113/buildings.geojson", generation=1)

    def download_to_filename(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("x", encoding="utf-8")

    for b in (walk, boundary, ward):
        b.download_to_filename.side_effect = download_to_filename

    bucket = MagicMock()
    bucket.blob.return_value = walk
    bucket.list_blobs.return_value = [walk, boundary, ward]
    client = MagicMock()
    client.bucket.return_value = bucket

    assert sync_processed(client=client, data_dir=tmp_path) == "synced"
    assert read_stamp(tmp_path) == "7"
    assert (tmp_path / "walk-graph.json").is_file()
    assert (tmp_path / "wards/13113/buildings.geojson").is_file()
    bucket.list_blobs.assert_called_once_with(prefix=prefix + "/")


def test_download_prefix_rejects_path_escape(tmp_path: Path):
    prefix = "processed/tokyo23"
    outside = tmp_path.parent / "outside.txt"
    client = MagicMock()
    bucket = MagicMock()
    client.bucket.return_value = bucket

    traversal = _blob(f"{prefix}/../../outside.txt")
    bucket.list_blobs.return_value = [traversal]
    with pytest.raises(ValueError, match="escapes|unsafe"):
        download_prefix(
            client=client, bucket_name="b", prefix=prefix, data_dir=tmp_path
        )
    traversal.download_to_filename.assert_not_called()
    assert not outside.exists()

    absolute = _blob(f"{prefix}//etc/passwd")
    bucket.list_blobs.return_value = [absolute]
    with pytest.raises(ValueError, match="escapes|unsafe"):
        download_prefix(
            client=client, bucket_name="b", prefix=prefix, data_dir=tmp_path
        )
    absolute.download_to_filename.assert_not_called()

    empty = _blob(f"{prefix}/.")
    bucket.list_blobs.return_value = [empty]
    download_prefix(client=client, bucket_name="b", prefix=prefix, data_dir=tmp_path)
    empty.download_to_filename.assert_not_called()
