from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

DEFAULT_GCS_URI = "gs://hikage-navi-data/processed/tokyo23"
STAMP_NAME = ".gcs-sync-stamp"
DEFAULT_DATA_DIR = Path("/data/tokyo23")


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"expected gs:// URI, got {uri!r}")
    rest = uri[5:]
    bucket, _, prefix = rest.partition("/")
    if not bucket or not prefix:
        raise ValueError(f"expected gs://bucket/prefix, got {uri!r}")
    return bucket, prefix.strip("/")


def sync_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get("HIKAGE_GCS_SYNC", "1")).strip().lower()
    return raw not in {"0", "false", "no"}


def stamp_path(data_dir: Path) -> Path:
    return data_dir / STAMP_NAME


def read_stamp(data_dir: Path) -> str | None:
    path = stamp_path(data_dir)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def write_stamp(data_dir: Path, generation: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = stamp_path(data_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(generation).strip() + "\n", encoding="utf-8")
    tmp.replace(path)


def local_ready(data_dir: Path) -> bool:
    return (data_dir / "walk-graph.json").is_file() and (
        data_dir / "boundary.geojson"
    ).is_file()


def should_skip_sync(data_dir: Path, remote_generation: str) -> bool:
    return local_ready(data_dir) and read_stamp(data_dir) == str(remote_generation)
