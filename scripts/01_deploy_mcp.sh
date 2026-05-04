#!/usr/bin/env bash
# ============================================================================
# 01_deploy_mcp.sh — Build & deploy the MCP server to Cloud Run
# ----------------------------------------------------------------------------
# This deploys the MCP server with --no-allow-unauthenticated, which is the
# zero-trust extra credit baseline. Only the agents' service account
# (acc-agents-sa) will be able to invoke this service.
#
# Usage:
#   export GCP_PROJECT=your-project-id
#   export GCP_REGION=us-central1     # optional
#   ./scripts/01_deploy_mcp.sh
# ============================================================================

set -euo pipefail

PROJECT="${GCP_PROJECT:?Set GCP_PROJECT first}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="acc-mcp-server"
SA_EMAIL="acc-agents-sa@${PROJECT}.iam.gserviceaccount.com"

# Repo dir = parent of scripts/
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Deploying $SERVICE_NAME to Cloud Run in $REGION (zero-trust mode)"
gcloud run deploy "$SERVICE_NAME" \
  --source="$REPO_DIR/mcp_server" \
  --region="$REGION" \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account="$SA_EMAIL" \
  --set-env-vars="GCP_PROJECT=$PROJECT" \
  --memory=512Mi \
  --cpu=1 \
  --timeout=60s \
  --max-instances=3 \
  --quiet

# Capture the deployed URL for downstream scripts
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" --format='value(status.url)')

echo
echo "============================================================"
echo " ✅ MCP server deployed."
echo
echo "   URL: $SERVICE_URL"
echo "   Auth: required (zero-trust)"
echo
echo " Save this URL — you'll need it for the agents:"
echo "   export MCP_URL=$SERVICE_URL"
echo
echo " Verify zero-trust is enforced (this should fail with 403):"
echo "   curl -i $SERVICE_URL/healthz"
echo
echo " Verify authenticated calls work:"
echo "   ./scripts/02_test_mcp.sh"
echo "============================================================"
