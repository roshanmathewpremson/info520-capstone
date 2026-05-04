"""
Career Specialist Agent ("Worker").

This agent is NEVER user-facing. It receives delegated tasks from the Supervisor
via A2A messages, decides which MCP tools to invoke, and returns structured
results. Backed by Gemini through the Vertex AI SDK with native function-calling.

Tools (MCP):
  - fetch_jobs(role, location, keyword)
  - sync_pipeline(action, job_data)
"""

import os
import json
import logging
from typing import Any

import vertexai
from vertexai.generative_models import (
    GenerativeModel, Tool, FunctionDeclaration, Part, Content,
)

from mcp_client import MCPClient


logger = logging.getLogger("acc.specialist")


SPECIALIST_SYSTEM_INSTRUCTION = """You are the Career Specialist agent in the Agentic Career Coach system.

You are NOT user-facing. You receive structured tasks from the Supervisor agent
and respond with structured results.

You have two MCP tools available:
  - fetch_jobs: search internship/job opportunities by role, location, keyword
  - sync_pipeline: manage the user's pipeline (create, list, update_status, delete)

Rules:
1. Always call a tool when one is appropriate — do not invent data.
2. After tool calls return, summarize the results concisely in your final response.
3. If a task requires multiple tool calls (e.g. fetch then save), do them in order.
4. Status values for sync_pipeline are exactly: saved, applied, interviewing, offer, rejected.
5. When asked to "save" or "track" a job, use sync_pipeline action=create.
6. Return JSON-serializable summaries, not prose, when the Supervisor will combine results.
"""


# ---------------------------------------------------------------------------
# Gemini function declarations — these mirror the MCP tool schemas
# ---------------------------------------------------------------------------
FETCH_JOBS_DECL = FunctionDeclaration(
    name="fetch_jobs",
    description="Search internship/job opportunities. All filters optional.",
    parameters={
        "type": "object",
        "properties": {
            "role": {"type": "string", "description": "Role keyword"},
            "location": {"type": "string", "description": "Location keyword"},
            "keyword": {"type": "string", "description": "Free-form keyword"},
        },
    },
)

SYNC_PIPELINE_DECL = FunctionDeclaration(
    name="sync_pipeline",
    description="CRUD on the internship pipeline in Firestore.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "update_status", "delete"],
            },
            "job_data": {"type": "object"},
        },
        "required": ["action"],
    },
)


class CareerSpecialistAgent:
    def __init__(self, mcp_url: str, project: str, location: str = "us-central1"):
        vertexai.init(project=project, location=location)
        self.mcp = MCPClient(mcp_url, use_oidc=True)
        self.tools = Tool(function_declarations=[FETCH_JOBS_DECL, SYNC_PIPELINE_DECL])
        self.model = GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=SPECIALIST_SYSTEM_INSTRUCTION,
            tools=[self.tools],
        )

    # -----------------------------------------------------------------
    # Entry point: handle a delegated task from the Supervisor
    # -----------------------------------------------------------------
    def handle_task(self, task: str) -> dict:
        """
        task: a structured instruction string from the Supervisor,
              e.g. "Find data analyst internships in Richmond and save them to my pipeline."
        Returns a structured result dict the Supervisor can compose into a user reply.
        """
        logger.info(f"[A2A IN] Specialist received task: {task}")

        chat = self.model.start_chat()
        response = chat.send_message(task)

        tool_call_log = []
        # Loop while the model wants to call tools
        for _ in range(6):  # safety limit on tool-call iterations
            candidate = response.candidates[0]
            part = candidate.content.parts[0]

            # Check if it's a function call
            if not getattr(part, "function_call", None) or not part.function_call.name:
                # Final natural-language response
                final_text = part.text if hasattr(part, "text") else str(part)
                logger.info(f"[A2A OUT] Specialist returning: {final_text[:140]}")
                return {
                    "summary": final_text,
                    "tool_calls": tool_call_log,
                }

            # Execute the tool via MCP
            fn_name = part.function_call.name
            fn_args = dict(part.function_call.args)
            logger.info(f"[MCP CALL] {fn_name}({fn_args})")
            try:
                tool_result = self.mcp.call_tool(fn_name, fn_args)
            except Exception as e:
                tool_result = {"error": str(e)}
                logger.exception(f"MCP tool {fn_name} failed")

            tool_call_log.append({
                "tool": fn_name, "arguments": fn_args, "result": tool_result,
            })

            # Feed the tool result back into the conversation
            response = chat.send_message(
                Part.from_function_response(name=fn_name, response={"content": tool_result})
            )

        return {
            "summary": "Specialist hit max tool iterations without final answer.",
            "tool_calls": tool_call_log,
        }
