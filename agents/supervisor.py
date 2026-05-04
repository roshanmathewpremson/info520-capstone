"""
Supervisor Agent ("Lead Orchestrator").

User-facing agent that parses high-level goals, decides when to delegate to the
Career Specialist via A2A handoff, and composes the final user-facing response.

The Supervisor has NO direct access to MCP tools — it can only delegate.
This is the architectural separation that makes this a true multi-agent system.
"""

import os
import json
import logging
from typing import Any

import vertexai
from vertexai.generative_models import (
    GenerativeModel, Tool, FunctionDeclaration, Part,
)

from specialist import CareerSpecialistAgent


logger = logging.getLogger("acc.supervisor")


SUPERVISOR_SYSTEM_INSTRUCTION = """You are the Supervisor agent (Lead Orchestrator) of the Agentic Career Coach.

You are user-facing. Your job:
1. Parse the user's high-level goal into a clear task.
2. Decide whether to delegate to the Career Specialist agent.
3. Take the Specialist's structured results and compose a friendly, concise reply.

You have ONE tool: `delegate_to_specialist(task)`. You do NOT have direct
access to job-search APIs or the user's pipeline. To do anything beyond
small talk or clarification, you MUST delegate.

Routing rules (prompt-based routing — this is the rubric requirement):
- If the user asks to FIND, SEARCH, or LIST jobs → delegate.
- If the user asks to SAVE, TRACK, ADD, UPDATE, or REMOVE a pipeline entry → delegate.
- If the user asks "what's in my pipeline" or "show my applications" → delegate.
- If the user asks something off-topic or just says hi → respond directly without delegating.

When delegating, write the task in plain natural language so the Specialist
can interpret it. Include all relevant constraints (location, role, status, etc.).

When you receive the Specialist's result, summarize it for the user in a warm,
human tone. Show concrete details (company names, deadlines, statuses).
"""


DELEGATE_DECL = FunctionDeclaration(
    name="delegate_to_specialist",
    description=(
        "Hand off a task to the Career Specialist agent. The task should be a "
        "single, self-contained natural-language instruction."
    ),
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Natural-language task for the Specialist",
            },
        },
        "required": ["task"],
    },
)


class SupervisorAgent:
    def __init__(self, mcp_url: str, project: str, location: str = "us-central1"):
        vertexai.init(project=project, location=location)
        self.specialist = CareerSpecialistAgent(mcp_url, project, location)
        self.tools = Tool(function_declarations=[DELEGATE_DECL])
        self.model = GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=SUPERVISOR_SYSTEM_INSTRUCTION,
            tools=[self.tools],
        )
        # Persistent chat across user turns within a session
        self.chat = self.model.start_chat()

    # -----------------------------------------------------------------
    # User-facing entry point
    # -----------------------------------------------------------------
    def handle_user_message(self, user_message: str) -> dict:
        logger.info(f"[USER] {user_message}")
        response = self.chat.send_message(user_message)

        delegation_log = []

        for _ in range(4):
            candidate = response.candidates[0]
            part = candidate.content.parts[0]

            if not getattr(part, "function_call", None) or not part.function_call.name:
                final_text = part.text if hasattr(part, "text") else str(part)
                logger.info(f"[ASSISTANT] {final_text[:140]}")
                return {
                    "reply": final_text,
                    "delegations": delegation_log,
                }

            # Supervisor wants to delegate
            if part.function_call.name != "delegate_to_specialist":
                logger.warning(f"Unexpected function: {part.function_call.name}")
                break

            task = dict(part.function_call.args).get("task", "")
            logger.info(f"[A2A HANDOFF →] Supervisor delegating: {task}")

            # === A2A HANDOFF ===
            specialist_result = self.specialist.handle_task(task)
            delegation_log.append({
                "task": task,
                "specialist_result": specialist_result,
            })
            logger.info(f"[A2A HANDOFF ←] Specialist returned summary")

            # Send specialist result back to Supervisor as function response
            response = self.chat.send_message(
                Part.from_function_response(
                    name="delegate_to_specialist",
                    response={"content": specialist_result},
                )
            )

        return {
            "reply": "I hit my delegation limit — please try again.",
            "delegations": delegation_log,
        }
