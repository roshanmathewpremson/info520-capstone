"""
Agentic Career Coach — MCP Server
==================================
FastAPI service implementing Model Context Protocol over Server-Sent Events.

Endpoints:
  GET  /            - Service health/info
  GET  /healthz     - Liveness probe for Cloud Run
  POST /messages    - JSON-RPC 2.0 entry point (single request/response)
  GET  /sse         - SSE streaming endpoint for long-lived agent connections

Tools exposed:
  - fetch_jobs(role, location, keyword)   - Returns matching internships
  - sync_pipeline(action, job_data)       - CRUD on Firestore pipeline

Run locally:
  uvicorn main:app --reload --port 8080

Deploy:
  See scripts/deploy_mcp.sh
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from tools import fetch_jobs_impl, sync_pipeline_impl, TOOLS_CATALOG
from firestore_client import get_firestore_client


# ---------------------------------------------------------------------------
# Logging — structured JSON for Cloud Logging
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k.startswith("ctx_"):
                payload[k[4:]] = v
        return json.dumps(payload)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
logger = logging.getLogger("acc.mcp")


# ---------------------------------------------------------------------------
# App lifecycle — initialize Firestore client on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "MCP server starting",
        extra={"ctx_project": os.getenv("GCP_PROJECT", "unknown")},
    )
    # Eagerly initialize Firestore client so first request is fast
    try:
        get_firestore_client()
        logger.info("Firestore client ready")
    except Exception as e:
        logger.error(f"Firestore init failed: {e}")
    yield
    logger.info("MCP server shutting down")


app = FastAPI(
    title="Agentic Career Coach — MCP Server",
    version="1.0.0",
    description="MCP-over-SSE backend for the ACC multi-agent system.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------
def jsonrpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def jsonrpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


# JSON-RPC 2.0 standard error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# Core MCP method dispatch
# ---------------------------------------------------------------------------
async def dispatch_mcp(method: str, params: dict, req_id: Any) -> dict:
    """Dispatch an MCP JSON-RPC call to the right handler."""
    logger.info(
        f"MCP method invoked: {method}",
        extra={"ctx_method": method, "ctx_request_id": str(req_id)},
    )

    # ---- MCP discovery method ----
    if method == "tools/list":
        return jsonrpc_result(req_id, {"tools": TOOLS_CATALOG})

    # ---- MCP tool invocation ----
    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name == "fetch_jobs":
            try:
                result = await fetch_jobs_impl(**tool_args)
                return jsonrpc_result(
                    req_id,
                    {"content": [{"type": "text", "text": json.dumps(result, default=str)}]},
                )
            except TypeError as e:
                return jsonrpc_error(req_id, INVALID_PARAMS, f"Bad arguments: {e}")
            except Exception as e:
                logger.exception("fetch_jobs failed")
                return jsonrpc_error(req_id, INTERNAL_ERROR, str(e))

        if tool_name == "sync_pipeline":
            try:
                result = await sync_pipeline_impl(**tool_args)
                return jsonrpc_result(
                    req_id,
                    {"content": [{"type": "text", "text": json.dumps(result, default=str)}]},
                )
            except TypeError as e:
                return jsonrpc_error(req_id, INVALID_PARAMS, f"Bad arguments: {e}")
            except Exception as e:
                logger.exception("sync_pipeline failed")
                return jsonrpc_error(req_id, INTERNAL_ERROR, str(e))

        return jsonrpc_error(req_id, METHOD_NOT_FOUND, f"Unknown tool: {tool_name}")

    # ---- MCP initialization handshake ----
    if method == "initialize":
        return jsonrpc_result(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "acc-mcp-server", "version": "1.0.0"},
            },
        )

    return jsonrpc_error(req_id, METHOD_NOT_FOUND, f"Unknown method: {method}")


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "service": "Agentic Career Coach — MCP Server",
        "version": "1.0.0",
        "transport": "MCP over Server-Sent Events",
        "endpoints": {
            "/healthz": "liveness probe",
            "/messages": "JSON-RPC 2.0 POST",
            "/sse": "SSE streaming",
        },
        "tools": [t["name"] for t in TOOLS_CATALOG],
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/messages")
async def messages(request: Request):
    """
    Single-shot JSON-RPC 2.0 endpoint.
    Used by clients that don't need long-lived SSE connections.
    """
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(jsonrpc_error(None, PARSE_ERROR, f"Parse error: {e}"))

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return JSONResponse(jsonrpc_error(body.get("id"), INVALID_REQUEST, "Not JSON-RPC 2.0"))

    method = body.get("method")
    params = body.get("params", {}) or {}
    req_id = body.get("id")

    if not method:
        return JSONResponse(jsonrpc_error(req_id, INVALID_REQUEST, "Missing method"))

    response = await dispatch_mcp(method, params, req_id)
    return JSONResponse(response)


@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    Server-Sent Events stream.
    Client connects here and receives streaming JSON-RPC frames.
    For this implementation, we send an initial `endpoint` event pointing back
    to /messages (per MCP SSE convention) plus a periodic keepalive.
    """
    async def event_stream():
        # MCP SSE convention: server first emits an `endpoint` event with the
        # POST URL the client should use for subsequent JSON-RPC calls.
        host = str(request.base_url).rstrip("/")
        endpoint_url = f"{host}/messages"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"

        # Keepalive every 15s so connection stays open behind Cloud Run LB
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("SSE client disconnected")
                    break
                await asyncio.sleep(15)
                yield ": keepalive\n\n"
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled")
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )


# ---------------------------------------------------------------------------
# Local dev entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
