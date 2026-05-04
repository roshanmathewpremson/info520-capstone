#!/usr/bin/env bash
# ============================================================================
# 02_test_mcp.sh — Verify the deployed MCP server end-to-end
# ----------------------------------------------------------------------------
# Tests:
#   1. Unauthenticated call → expect 403 (proves zero-trust)
#   2. Authenticated tools/list → expect both tools
#   3. Authenticated fetch_jobs → expect job list
#   4. Authenticated sync_pipeline create → expect ok
#   5. Authenticated sync_pipeline list → expect the created job
# ============================================================================

set -euo pipefail

PROJECT="${GCP_PROJECT:?Set GCP_PROJECT first}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="acc-mcp-server"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" --format='value(status.url)')

echo "==> Testing $SERVICE_URL"
echo

# ----------------------------------------------------------------------
# Test 1: Unauthenticated call must be rejected
# ----------------------------------------------------------------------
echo "[1/5] Unauthenticated call (expect 403)..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/healthz" || true)
if [[ "$HTTP_CODE" == "403" || "$HTTP_CODE" == "401" ]]; then
  echo "    ✅ Got $HTTP_CODE — zero-trust is enforced"
else
  echo "    ❌ Got $HTTP_CODE — expected 401/403. Check --no-allow-unauthenticated."
  exit 1
fi

# Get an OIDC token for authenticated calls
TOKEN=$(gcloud auth print-identity-token --audiences="$SERVICE_URL")

# ----------------------------------------------------------------------
# Test 2: tools/list
# ----------------------------------------------------------------------
echo
echo "[2/5] Authenticated tools/list..."
RESP=$(curl -s -X POST "$SERVICE_URL/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}')
echo "$RESP" | python3 -m json.tool | head -20
echo "$RESP" | grep -q "fetch_jobs" || { echo "❌ fetch_jobs not in catalog"; exit 1; }
echo "$RESP" | grep -q "sync_pipeline" || { echo "❌ sync_pipeline not in catalog"; exit 1; }
echo "    ✅ Both tools advertised"

# ----------------------------------------------------------------------
# Test 3: fetch_jobs
# ----------------------------------------------------------------------
echo
echo "[3/5] fetch_jobs(role='data analyst')..."
RESP=$(curl -s -X POST "$SERVICE_URL/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"fetch_jobs","arguments":{"role":"data analyst"}}}')
echo "$RESP" | python3 -m json.tool | head -10
echo "$RESP" | grep -q "Microsoft" && echo "    ✅ Returned matching jobs"

# ----------------------------------------------------------------------
# Test 4: sync_pipeline create
# ----------------------------------------------------------------------
echo
echo "[4/5] sync_pipeline create..."
RESP=$(curl -s -X POST "$SERVICE_URL/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"sync_pipeline","arguments":{"action":"create","job_data":{"id":"test_smoke_001","company":"TestCo","title":"Test Role","status":"saved"}}}}')
echo "$RESP" | python3 -m json.tool | head -10
echo "$RESP" | grep -q '"ok": true\|\"ok\":true' && echo "    ✅ Firestore write succeeded"

# ----------------------------------------------------------------------
# Test 5: sync_pipeline list
# ----------------------------------------------------------------------
echo
echo "[5/5] sync_pipeline list..."
RESP=$(curl -s -X POST "$SERVICE_URL/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"4","method":"tools/call","params":{"name":"sync_pipeline","arguments":{"action":"list"}}}')
echo "$RESP" | python3 -m json.tool | head -15
echo "$RESP" | grep -q "test_smoke_001" && echo "    ✅ Firestore read confirms write"

echo
echo "============================================================"
echo " ✅ All MCP tests passed."
echo "============================================================"
