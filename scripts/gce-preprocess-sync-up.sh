#!/usr/bin/env bash
# Push VM data/raw and data/processed/tokyo23 to GCS (canonical store).
# Requires VM to be RUNNING. Repo path on VM: HIKAGE_GCE_REPO (default ~/hikage-navi).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=gce-env.sh
source "$ROOT/scripts/gce-env.sh"

REPO_ON_VM="${HIKAGE_GCE_REPO:-\$HOME/hikage-navi}"

echo "Sync VM → ${HIKAGE_GCS_BUCKET} (raw + processed/tokyo23)…"
gcloud compute ssh "$HIKAGE_GCE_INSTANCE" --zone="$HIKAGE_GCE_ZONE" --command="
set -euo pipefail
cd ${REPO_ON_VM}
test -d data/processed/tokyo23 || { echo 'missing data/processed/tokyo23 — run preprocess first' >&2; exit 1; }
gsutil -m rsync -r data/raw '${HIKAGE_GCS_BUCKET}/raw'
gsutil -m rsync -r data/processed/tokyo23 '${HIKAGE_GCS_BUCKET}/processed/tokyo23'
echo 'GCS sync-up done.'
"
