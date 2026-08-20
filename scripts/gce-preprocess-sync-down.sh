#!/usr/bin/env bash
# Pull processed/tokyo23 from GCS to this Mac (no raw / CityGML zips).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=gce-env.sh
source "$ROOT/scripts/gce-env.sh"

DEST="$ROOT/data/processed/tokyo23"
mkdir -p "$DEST"
echo "Sync ${HIKAGE_GCS_BUCKET}/processed/tokyo23 → ${DEST}…"
gsutil -m rsync -r "${HIKAGE_GCS_BUCKET}/processed/tokyo23" "$DEST"
echo "Done. Example:"
echo "  export HIKAGE_DATA_DIR=${DEST}"
