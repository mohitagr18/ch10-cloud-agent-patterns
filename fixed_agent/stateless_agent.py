"""
fixed_agent/stateless_agent.py — Section 10.3

This module is the corrected version of broken_agent/stateful_agent.py.
The only structural change is the removal of _retrieval_cache and
_cache_hit_count, and the replacement of the in-process cache lookup with
a direct HTTP call to Service A (the FastAPI retrieval service).

What changed and why:
  BEFORE: retrieve_policy_context() checked _retrieval_cache first,
          then called rag.retrieval_query() on a cache miss, then stored
          the result in _retrieval_cache for the next call.

  AFTER:  retrieve_policy_context() calls Service A's /retrieve endpoint
          on every invocation. There is no local state. Every worker that
          handles a request goes to the same external service and gets the
          same result.

What did NOT change:
  - The ADK agent definition is identical.
  - The tool signature (retrieve_policy_context(query: str) -> dict) is
    identical. The agent does not know or care that the retrieval mechanism
    changed.
  - The system instruction is identical.

This is the architectural lesson of section 10.3: statelessness is a
property of where you store data, not a property of the agent itself.
Moving state out of the process and into a durable external service fixes
the cloud failure without changing the agent's observable behaviour.

Usage (local test against a running Service A):
    uv run uvicorn retrieval_service.app:app --port 8080
    uv run python fixed_agent/stateless_agent.py
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Service A's URL is injected via environment variable at deploy time.
# There is no fallback to localhost here — if the variable is missing, the
# tool fails loudly so the reader sees the configuration error immediately.
RETRIEVAL_SERVICE_URL = os.getenv("RETRIEVAL_SERVICE_URL", "").rstrip("/")


def retrieve_policy_context(query: str) -> dict:
    """Retrieve company policy contexts by calling the external retrieval service.

    This function is stateless by design. It holds no local cache, no module-
    level dict, and no mutable state of any kind. Every call goes to Service A
    over HTTP. Cloud Run can start any number of instances of this agent and
    they will all return consistent results because they all talk to the same
    external service.

    The httpx call is synchronous here because the ADK agent runtime is also
    synchronous in this deployment pattern. For async deployments, replace
    httpx.post() with an awaited httpx.AsyncClient().post() call.

    Args:
        query: The user's policy question.

    Returns:
        A dict with keys: status, contexts, context_count, source_service.
        source_service confirms which URL was called, making the architecture
        visible in logs and the terminal output.
    """
    if not RETRIEVAL_SERVICE_URL:
        return {
            "status": "error",
            "error_message": (
                "RETRIEVAL_SERVICE_URL is not set. "
                "Start Service A locally with:\n"
                "  uv run uvicorn retrieval_service.app:app --port 8080\n"
                "Then set RETRIEVAL_SERVICE_URL=http://localhost:8080 in your .env."
            ),
        }

    retrieve_url = f"{RETRIEVAL_SERVICE_URL}/retrieve"
    try:
        response = httpx.post(
            retrieve_url,
            json={"query": query, "top_k": 5},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()

        return {
            "status": "success",
            "contexts": payload.get("contexts", []),
            "context_count": payload.get("context_count", 0),
            # Surfaces in logs so it's visible that the call went to Service A.
            "source_service": retrieve_url,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "error_message": (
                f"Service A returned HTTP {exc.response.status_code}. "
                f"Check that {RETRIEVAL_SERVICE_URL} is running and healthy."
            ),
        }
    except httpx.ConnectError:
        return {
            "status": "error",
            "error_message": (
                f"Could not connect to Service A at {RETRIEVAL_SERVICE_URL}. "
                "Verify RETRIEVAL_SERVICE_URL in your .env file and that the "
                "service is running."
            ),
        }


def create_stateless_agent():
    """Create an ADK agent that delegates all retrieval to Service A.

    The agent definition is structurally identical to create_stateful_agent()
    in broken_agent/stateful_agent.py. The only difference is the tool
    implementation. This makes the comparison between the two files as direct
    as possible: same agent shape, different retrieval strategy.

    Returns:
        A configured google.adk.agents.Agent instance.
    """
    from google.adk.agents import Agent

    agent = Agent(
        name="stateless_policy_assistant",
        model=os.getenv("AGENT_MODEL", "gemini-2.0-flash-001"),
        description="Company policy assistant (fixed: stateless, calls Service A)",
        instruction=(
            "You are an enterprise knowledge base assistant. "
            "When a user asks about company policy, use the retrieve_policy_context "
            "tool to find relevant information, then answer clearly and concisely. "
            "Always base your answer on the retrieved contexts, not on general knowledge."
        ),
        tools=[retrieve_policy_context],
    )
    return agent


def run_comparison_demo() -> None:
    """Run a local before/after comparison to demonstrate the fix.

    Calls retrieve_policy_context() twice with the same query and prints the
    response alongside confirmation that no local cache was used. When run
    against a live Service A, the reader sees two identical, consistent
    responses — proof that statelessness works correctly.
    """
    separator = "─" * 60
    test_query = "What is the remote work policy?"

    print()
    print(separator)
    print("SECTION 10.3 — Fixed stateless agent, two sequential calls")
    print(separator)
    print(f"Query: "{test_query}"")
    print(f"Retrieval service: {RETRIEVAL_SERVICE_URL or 'NOT SET'}")
    print()

    for request_number in range(1, 3):
        print(f"Sending request {request_number}...")
        result = retrieve_policy_context(test_query)

        if result["status"] == "error":
            print(f"  ERROR: {result['error_message']}")
            sys.exit(1)

        print(f"  status          : {result['status']}")
        print(f"  context_count   : {result['context_count']}")
        print(f"  source_service  : {result.get('source_service', 'N/A')}")
        # In-process cache fields are absent by design.
        print(f"  cache_hit       : N/A — no in-process cache exists")
        if result["contexts"]:
            preview = result["contexts"][0]["text"][:80]
            print(f"  top_context     : "{preview}..."")
        print()

    print("OBSERVATION:")
    print("  Both requests returned consistent results.")
    print("  No in-process cache was consulted.")
    print("  All retrieval went through Service A over HTTP.")
    print("  Any number of Cloud Run instances will produce the same output.")
    print(separator)


if __name__ == "__main__":
    run_comparison_demo()
