"""
broken_agent/run_stateless_failure.py — Sections 10.1 and 10.2

This script sends real HTTP requests to a deployed Cloud Run endpoint and
makes the statelessness failure visible in the terminal. It does not simulate
anything: the requests hit live infrastructure, and the output reflects what
actually happened in the cloud.

Section 10.1 — Sequential failure
  Two requests, same query, sent one after the other. If they land on
  different container instances (which Cloud Run's autoscaler routinely
  causes, especially with min-instances=0), the second request will show
  cache_hits=0 even though the first request populated its own cache.

Section 10.2 — Concurrent failure
  Two requests fired simultaneously with asyncio.gather. Concurrent load
  is the fastest way to force Cloud Run to split traffic across instances.
  Both responses will show cache_hits=0 regardless of instance assignment.

How to read the output:
  container_id — the Cloud Run revision+instance identifier injected by the
                 agent service (see agent_service/app.py). When two requests
                 show different container_ids, they ran in separate processes.
  cache_hits   — how many times the in-process cache was consulted in that
                 container's lifetime. Zero means the cache never helped.

Usage:
    uv run python broken_agent/run_stateless_failure.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# The broken agent service is Service B deployed with the stateful agent.
# After running scripts/deploy_service_b_broken.sh, set this URL in your .env.
AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "").rstrip("/")
TEST_QUERY = "What is the remote work policy?"
REQUEST_TIMEOUT = 60.0  # Cloud Run cold starts can be slow


def check_url_configured() -> None:
    """Exit with a clear message if AGENT_SERVICE_URL is not set.

    Catching this here prevents a confusing ConnectionError from httpx
    that would obscure the real problem.
    """
    if not AGENT_SERVICE_URL:
        print(
            "AGENT_SERVICE_URL is not set.\n"
            "Deploy the broken agent service first:\n"
            "  bash scripts/deploy_service_b_broken.sh\n"
            "Then set AGENT_SERVICE_URL in your .env file."
        )
        sys.exit(1)


def send_query(client: httpx.Client, label: str) -> dict:
    """Send a single synchronous query to the agent service.

    Returns the full response dict including the diagnostic fields
    container_id and cache_hits that the service injects into every response.

    Args:
        client: A shared httpx.Client (connection pooling improves timing accuracy).
        label:  A short label printed in the terminal to identify this request.

    Returns:
        The parsed JSON response body, or an error dict on failure.
    """
    print(f"  [{label}] Sending POST {AGENT_SERVICE_URL}/query ...")
    try:
        response = client.post(
            f"{AGENT_SERVICE_URL}/query",
            json={"query": TEST_QUERY},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}", "body": exc.response.text[:200]}
    except Exception as exc:
        return {"error": str(exc)}


async def send_query_async(label: str) -> dict:
    """Send a single async query to the agent service.

    Used in Section 10.2 to fire two requests concurrently. Each call
    creates its own AsyncClient so there is no shared connection state
    that might serialise the requests.

    Args:
        label: A short label printed in the terminal to identify this request.

    Returns:
        The parsed JSON response body, or an error dict on failure.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{AGENT_SERVICE_URL}/query",
                json={"query": TEST_QUERY},
            )
            response.raise_for_status()
            return {"label": label, **response.json()}
        except httpx.HTTPStatusError as exc:
            return {"label": label, "error": f"HTTP {exc.response.status_code}"}
        except Exception as exc:
            return {"label": label, "error": str(exc)}


def print_response(label: str, result: dict) -> None:
    """Print the diagnostic fields from a single response in a readable format."""
    if "error" in result:
        print(f"  [{label}] ERROR: {result['error']}")
        return

    container_id = result.get("container_id", "unknown")
    cache_hits = result.get("cache_hits", "N/A")
    context_count = len(result.get("contexts", []))
    answer_preview = str(result.get("answer", ""))[:80]

    print(f"  [{label}] container_id : {container_id}")
    print(f"  [{label}] cache_hits   : {cache_hits}")
    print(f"  [{label}] contexts     : {context_count}")
    print(f"  [{label}] answer       : {answer_preview}...")


def run_section_10_1() -> tuple[str, str]:
    """Section 10.1 — sequential statelessness failure.

    Sends two requests one after the other. Returns the container IDs
    from each response so the caller can check whether they differ.

    Returns:
        (container_id_request_1, container_id_request_2)
    """
    separator = "─" * 60
    print()
    print(separator)
    print("SECTION 10.1 — Sequential requests, in-process cache")
    print(separator)
    print(f"Query: "{TEST_QUERY}"")
    print()

    with httpx.Client() as client:
        print("Sending request 1...")
        result_1 = send_query(client, "Request 1")
        print_response("Request 1", result_1)

        print()
        print("Sending request 2 (same query)...")
        result_2 = send_query(client, "Request 2")
        print_response("Request 2", result_2)

    container_1 = result_1.get("container_id", "unknown")
    container_2 = result_2.get("container_id", "unknown")

    print()
    if container_1 != container_2:
        print("OBSERVATION: Requests landed on DIFFERENT container instances.")
        print(f"  Container 1: {container_1}")
        print(f"  Container 2: {container_2}")
        print("  Request 1 populated its cache, but Request 2 never saw it.")
        print("  cache_hits is 0 on Request 2. In-process state is not shared.")
    else:
        print("OBSERVATION: Both requests landed on the SAME container instance.")
        print(f"  Container: {container_1}")
        print("  To force a split, run this script again or increase load.")
        print("  Section 10.2 uses concurrent requests to reliably force a split.")

    return container_1, container_2


async def run_section_10_2() -> None:
    """Section 10.2 — concurrent statelessness failure.

    Fires two requests simultaneously using asyncio.gather. Concurrent load
    is the most reliable way to force Cloud Run to route traffic to separate
    container instances, making the memory loss guaranteed rather than
    probabilistic.
    """
    separator = "─" * 60
    print()
    print(separator)
    print("SECTION 10.2 — Concurrent requests, memory loss guaranteed")
    print(separator)
    print(f"Query: "{TEST_QUERY}"")
    print()
    print("Firing 2 requests simultaneously with asyncio.gather...")
    print()

    # Fire both requests at the same moment. Cloud Run will route them to
    # separate instances because a single instance handles one request at a time
    # in this configuration.
    results = await asyncio.gather(
        send_query_async("Worker A"),
        send_query_async("Worker B"),
    )

    for result in results:
        label = result.get("label", "?")
        print_response(label, result)
        print()

    container_a = results[0].get("container_id", "unknown")
    container_b = results[1].get("container_id", "unknown")
    unique_containers = len({container_a, container_b})

    print("OBSERVATION:")
    print(f"  concurrent_requests : 2")
    print(f"  unique_containers   : {unique_containers}")
    print(f"  shared_state        : {unique_containers == 1}")
    print()
    if unique_containers > 1:
        print("  Both workers started with empty caches.")
        print("  Neither worker saw the other's retrieval results.")
        print("  This is not a bug — it is the design of stateless compute.")
        print("  The fix is in fixed_agent/stateless_agent.py.")
    else:
        print("  Both requests landed on the same instance this time.")
        print("  Re-run to observe the split. Section 10.3 shows the fix.")


def main() -> None:
    """Entry point: run both demonstration sections in sequence."""
    check_url_configured()
    run_section_10_1()
    asyncio.run(run_section_10_2())
    print()
    print("─" * 60)
    print("Next step: run fixed_agent/stateless_agent.py to see the fix.")
    print("─" * 60)


if __name__ == "__main__":
    main()
