#!/usr/bin/env bash
# ============================================================================
# 03_run_agents.sh — Run the multi-agent system locally
# ----------------------------------------------------------------------------
# Pulls the deployed Cloud Run URL automatically and starts the chat CLI.
# The Supervisor agent (user-facing) runs in your terminal and delegates to
# the Career Specialist agent, which calls MCP tools on Cloud Run.
# ============================================================================

set -euo pipefail

PROJECT="${GCP_PROJECT:?Set GCP_PROJECT first}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="acc-mcp-server"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export MCP_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" --format='value(status.url)')

if [[ -z "${MCP_URL:-}" ]]; then
  echo "❌ Could not resolve MCP_URL — has the MCP server been deployed?"
  exit 1
fi

echo "==> Project:  $PROJECT"
echo "==> MCP URL:  $MCP_URL"
echo

# Install agent deps if needed
if [[ ! -d "$REPO_DIR/agents/.venv" ]]; then
  echo "==> Setting up Python venv for agents..."
  python3 -m venv "$REPO_DIR/agents/.venv"
  "$REPO_DIR/agents/.venv/bin/pip" install --quiet -r "$REPO_DIR/agents/requirements.txt"
fi

cd "$REPO_DIR/agents"
exec ./.venv/bin/python chat_cli.py
