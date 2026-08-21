from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path

DEFAULT_GCS_URI = "gs://hikage-navi-data/processed/tokyo23"
STAMP_NAME = ".gcs-sync-stamp"
DEFAULT_DATA_DIR = Path("/data/tokyo23")

logger = logging.getLogger(__name__)


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


def remote_walk_graph_generation(client, bucket_name: str, prefix: str) -> str:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"{prefix}/walk-graph.json")
    blob.reload()
    if getattr(blob, "generation", None) is None:
        raise FileNotFoundError(f"gs://{bucket_name}/{prefix}/walk-graph.json missing")
    return str(blob.generation)


def download_prefix(*, client, bucket_name: str, prefix: str, data_dir: Path) -> None:
    bucket = client.bucket(bucket_name)
    list_prefix = prefix if prefix.endswith("/") else prefix + "/"
    data_dir.mkdir(parents=True, exist_ok=True)
    for blob in bucket.list_blobs(prefix=list_prefix):
        name = blob.name
        if name.endswith("/"):
            continue
        rel = name[len(list_prefix) :]
        if not rel:
            continue
        dest = data_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))


def sync_processed(
    *,
    client=None,
    gcs_uri: str | None = None,
    data_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = environ if environ is not None else os.environ
    if not sync_enabled(env):
        logger.info("gcs_sync disabled (HIKAGE_GCS_SYNC)")
        return "disabled"
    uri = gcs_uri or env.get("HIKAGE_GCS_PROCESSED_URI") or DEFAULT_GCS_URI
    dest = Path(data_dir or env.get("HIKAGE_DATA_DIR") or DEFAULT_DATA_DIR)
    bucket_name, prefix = parse_gcs_uri(uri)
    if client is None:
        from google.cloud import storage

        client = storage.Client()
    generation = remote_walk_graph_generation(client, bucket_name, prefix)
    if should_skip_sync(dest, generation):
        logger.info("gcs_sync skip generation=%s dir=%s", generation, dest)
        return "skipped"
    logger.info("gcs_sync download generation=%s uri=%s -> %s", generation, uri, dest)
    download_prefix(client=client, bucket_name=bucket_name, prefix=prefix, data_dir=dest)
    if not local_ready(dest):
        raise RuntimeError(f"sync incomplete: missing walk-graph/boundary under {dest}")
    write_stamp(dest, generation)
    return "synced"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = sync_processed()
        logger.info("gcs_sync done: %s", result)
    except Exception:
        logger.exception("gcs_sync failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
