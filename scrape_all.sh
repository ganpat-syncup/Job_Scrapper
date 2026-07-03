#!/usr/bin/env bash
# Scrape all latest jobs (no filters) and import into SyncUp ExternalJob DB.
set -euo pipefail
cd "$(dirname "$0")"

export SKIP_LOCAL_PUSH="${SKIP_LOCAL_PUSH:-true}"
export HEADLESS="${HEADLESS:-true}"
export SYNCUP_IMPORT_URL="${SYNCUP_IMPORT_URL:-http://localhost:6001/api/job-service/job/external/import}"
export SYNCUP_IMPORT_API_KEY="${SYNCUP_IMPORT_API_KEY:-local-dev-import-key}"

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

"$PYTHON" scrape_all.py
