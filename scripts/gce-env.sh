#!/usr/bin/env bash
# Shared env for GCE preprocess helpers. Source from sibling scripts.
set -euo pipefail

: "${HIKAGE_GCP_PROJECT:?Set HIKAGE_GCP_PROJECT (GCP project id)}"
: "${HIKAGE_GCE_ZONE:=asia-northeast1-a}"
: "${HIKAGE_GCE_INSTANCE:=hikage-preprocess}"
: "${HIKAGE_GCS_BUCKET:=gs://${HIKAGE_GCP_PROJECT}-hikage-navi}"

export HIKAGE_GCE_ZONE HIKAGE_GCE_INSTANCE HIKAGE_GCS_BUCKET

gcloud config set project "$HIKAGE_GCP_PROJECT" >/dev/null
