#!/usr/bin/env bash
# ============================================================================
# run_mcp_local.sh — Run MCP server on localhost:8080 for development
# ----------------------------------------------------------------------------
# Set GOOGLE_APPLICATION_CREDENTIALS or run `gcloud auth application-default login`
# so the local server can talk to Firestore.
# ============================================================================

set -euo pipefail

PROJECT="${GCP_PROJECT:?Set GCP_PROJECT first}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_DIR/mcp_server"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

export GCP_PROJECT="$PROJECT"
exec ./.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 --reload
