"""
Interactive CLI — talk to the Supervisor agent.

Usage:
  export GCP_PROJECT=your-project-id
  export MCP_URL=https://acc-mcp-server-XXXX.run.app
  python chat_cli.py

Type your message and press Enter. Type 'exit' to quit.
"""

import os
import sys
import json
import logging

from supervisor import SupervisorAgent


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    project = os.getenv("GCP_PROJECT")
    mcp_url = os.getenv("MCP_URL")
    if not project or not mcp_url:
        print("ERROR: set GCP_PROJECT and MCP_URL environment variables", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("  Agentic Career Coach — Interactive Demo")
    print("=" * 70)
    print(f"  Project:   {project}")
    print(f"  MCP URL:   {mcp_url}")
    print("  Type your message. Examples:")
    print("    - find me data analyst internships in Richmond")
    print("    - save the Capital One ML role to my pipeline")
    print("    - what's in my pipeline?")
    print("    - mark the Capital One role as applied")
    print("  Type 'exit' to quit.")
    print("=" * 70)
    print()

    supervisor = SupervisorAgent(mcp_url=mcp_url, project=project)

    while True:
        try:
            msg = input("you > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
            break
        if not msg:
            continue
        if msg.lower() in ("exit", "quit", ":q"):
            print("bye")
            break
        try:
            result = supervisor.handle_user_message(msg)
        except Exception as e:
            print(f"[error] {e}")
            continue
        print(f"\nassistant > {result['reply']}\n")
        if result.get("delegations"):
            print(f"  ({len(result['delegations'])} A2A handoff(s) this turn)\n")


if __name__ == "__main__":
    main()
