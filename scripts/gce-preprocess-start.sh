#!/usr/bin/env bash
# Start the preprocess VM (pay for compute only while running).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=gce-env.sh
source "$ROOT/scripts/gce-env.sh"

echo "Starting ${HIKAGE_GCE_INSTANCE} in ${HIKAGE_GCE_ZONE}…"
gcloud compute instances start "$HIKAGE_GCE_INSTANCE" --zone="$HIKAGE_GCE_ZONE"
echo "Ready. SSH:"
echo "  gcloud compute ssh ${HIKAGE_GCE_INSTANCE} --zone=${HIKAGE_GCE_ZONE}"
