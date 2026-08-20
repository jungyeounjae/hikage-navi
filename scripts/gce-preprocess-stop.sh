#!/usr/bin/env bash
# Stop the preprocess VM (disk charges remain; compute stops).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=gce-env.sh
source "$ROOT/scripts/gce-env.sh"

echo "Stopping ${HIKAGE_GCE_INSTANCE}…"
gcloud compute instances stop "$HIKAGE_GCE_INSTANCE" --zone="$HIKAGE_GCE_ZONE"
echo "Stopped."
