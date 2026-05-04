#!/usr/bin/env bash
# ============================================================================
# 00_bootstrap.sh — One-time GCP setup for the ACC project
# ----------------------------------------------------------------------------
# Run this ONCE after creating your GCP project. It:
#   1. Sets your active project
#   2. Enables required APIs
#   3. Creates a service account for the agents
#   4. Grants minimal IAM roles
#   5. Creates the Firestore database (Native mode, default)
#
# Usage:
#   export GCP_PROJECT=your-project-id     # set this first!
#   export GCP_REGION=us-central1          # optional, defaults to us-central1
#   ./scripts/00_bootstrap.sh
# ============================================================================

set -euo pipefail

PROJECT="${GCP_PROJECT:?Set GCP_PROJECT first}"
REGION="${GCP_REGION:-us-central1}"
SA_NAME="acc-agents-sa"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

echo "==> Setting active project: $PROJECT"
gcloud config set project "$PROJECT"

echo "==> Enabling required APIs (this can take 1-2 min)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com

echo "==> Creating service account: $SA_EMAIL"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --quiet 2>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="ACC Agents Service Account"
else
  echo "    (already exists)"
fi

echo "==> Granting IAM roles..."
for ROLE in \
  roles/datastore.user \
  roles/aiplatform.user \
  roles/run.invoker \
  roles/logging.logWriter \
  roles/cloudtrace.agent
do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE" \
    --condition=None \
    --quiet >/dev/null
  echo "    granted $ROLE"
done

echo "==> Creating Firestore database (Native mode, region $REGION)..."
if ! gcloud firestore databases describe --database='(default)' --quiet 2>/dev/null; then
  gcloud firestore databases create \
    --location="$REGION" \
    --type=firestore-native
else
  echo "    (already exists)"
fi

echo
echo "============================================================"
echo " ✅ Bootstrap complete."
echo
echo " Next steps:"
echo "   1. Deploy the MCP server:    ./scripts/01_deploy_mcp.sh"
echo "   2. Test it locally:          ./scripts/02_test_mcp.sh"
echo "   3. Run the agents:           ./scripts/03_run_agents.sh"
echo
echo " Environment to remember:"
echo "   GCP_PROJECT=$PROJECT"
echo "   GCP_REGION=$REGION"
echo "   SA_EMAIL=$SA_EMAIL"
echo "============================================================"
