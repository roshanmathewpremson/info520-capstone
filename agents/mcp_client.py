"""
MCP client for the Career Specialist agent.

Talks to the deployed Cloud Run MCP server using JSON-RPC 2.0.
Uses the /messages endpoint for request/response and /sse for the
handshake. Attaches a signed OIDC ID token on every call when configured
for zero-trust mode.
"""

import os
import json
import uuid
import logging
import requests
from typing import Any, Optional


logger = logging.getLogger("acc.mcp_client")


class MCPClient:
    """
    Synchronous MCP client. Uses /messages for the actual JSON-RPC traffic;
    SSE handshake is performed lazily when needed.
    """

    def __init__(self, base_url: str, use_oidc: bool = True, audience: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.messages_url = f"{self.base_url}/messages"
        self.use_oidc = use_oidc
        self.audience = audience or self.base_url
        self._session = requests.Session()

    # -----------------------------------------------------------------
    # OIDC identity token (zero-trust extra credit)
    # -----------------------------------------------------------------
    def _get_identity_token(self) -> Optional[str]:
        """
        Fetch a signed OIDC ID token from the GCP metadata server.
        Works on Cloud Run, GCE, and Vertex AI service accounts.
        Locally, falls back to `gcloud auth print-identity-token`.
        """
        if not self.use_oidc:
            return None

        # Cloud Run / GCE metadata server
        try:
            md_url = (
                "http://metadata.google.internal/computeMetadata/v1/"
                f"instance/service-accounts/default/identity?audience={self.audience}"
            )
            resp = requests.get(
                md_url, headers={"Metadata-Flavor": "Google"}, timeout=2
            )
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass

        # Local dev fallback
        try:
            import subprocess
            result = subprocess.run(
                ["gcloud", "auth", "print-identity-token", f"--audiences={self.audience}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        logger.warning("Could not obtain OIDC token; calls may fail if Cloud Run requires auth")
        return None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        token = self._get_identity_token()
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    # -----------------------------------------------------------------
    # JSON-RPC helpers
    # -----------------------------------------------------------------
    def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }
        logger.info(f"MCP call → {method}")
        resp = self._session.post(
            self.messages_url, json=payload, headers=self._headers(), timeout=30
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"MCP error: {body['error']}")
        return body.get("result", {})

    # -----------------------------------------------------------------
    # MCP API surface
    # -----------------------------------------------------------------
    def initialize(self) -> dict:
        return self._rpc("initialize", {})

    def list_tools(self) -> list[dict]:
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        # Tool results come back as MCP content blocks; unwrap the JSON we packed
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except json.JSONDecodeError:
                return content[0]["text"]
        return result
