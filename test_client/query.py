"""
test_client/query.py — Reader-facing query client for Section 10.5.

This tiny client sends a real HTTP request to the deployed agent backend so
readers can verify the final stack without writing curl commands by hand.

Why this matters for the chapter:
  The chapter is about cloud deployment patterns, not shell fluency. A small
  Python client makes the final end-to-end test easy to reproduce and easy to
  inspect.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def main() -> None:
    """Send a policy question to the deployed agent backend and print the result.

    The script is intentionally simple and reader-facing. It validates that the
    AGENT_SERVICE_URL is set, sends one question, and prints the structured JSON
    response fields that matter for the chapter demonstration.
    """
    agent_service_url = os.getenv("AGENT_SERVICE_URL", "").rstrip("/")
    if not agent_service_url:
        print(
            "AGENT_SERVICE_URL is not set. Add it to your .env file after deploying Service B.
"
            "Example: AGENT_SERVICE_URL=https://policy-agent-abc123-uc.a.run.app"
        )
        sys.exit(1)

    query_text = "What is the remote work policy?"
    response = httpx.post(
        f"{agent_service_url}/query",
        json={"query": query_text},
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()

    print("Section 10.5 — End-to-end query client")
    print(f"Service URL     : {agent_service_url}")
    print(f"Query           : {query_text}")
    print(f"Answer          : {payload.get('answer', '')}")
    print(f"Context count   : {payload.get('context_count', 0)}")
    print(f"Execution path  : {payload.get('execution_path', 'N/A')}")
    print(f"Container ID    : {payload.get('container_id', 'N/A')}")


if __name__ == "__main__":
    main()
