"""
validate_services.py — Section 10.5

Checks that both deployed Cloud Run services are healthy and that the complete
end-to-end query path works:
  Client -> Service B (/query) -> Service A (/retrieve) -> Vertex AI RAG Engine

This is the chapter's final proof that the cloud agent architecture is working.
The output is designed for readers: clear pass/fail lines, response times, and
specific remediation messages for the most likely deployment mistakes.

Usage:
    uv run python validate_services.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

RETRIEVAL_SERVICE_URL = os.getenv("RETRIEVAL_SERVICE_URL", "").rstrip("/")
AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "").rstrip("/")
TEST_QUERY = "What is the expense reimbursement policy?"
TIMEOUT_SECONDS = 60.0


def require_url(name: str, value: str) -> None:
    """Exit early with a reader-friendly error if a service URL is missing."""
    if not value:
        print(
            f"{name} is not set. Populate it in your .env file after deployment.\n"
            f"Example: {name}=https://your-service-name-abc123-uc.a.run.app"
        )
        sys.exit(1)


def timed_get(client: httpx.Client, url: str) -> tuple[int, float, dict | str]:
    """Send a GET request and return status, elapsed ms, and parsed body."""
    start = time.perf_counter()
    response = client.get(url, timeout=TIMEOUT_SECONDS)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    try:
        body = response.json()
    except Exception:
        body = response.text[:200]
    return response.status_code, elapsed_ms, body


def timed_post(client: httpx.Client, url: str, payload: dict) -> tuple[int, float, dict | str]:
    """Send a POST request and return status, elapsed ms, and parsed body."""
    start = time.perf_counter()
    response = client.post(url, json=payload, timeout=TIMEOUT_SECONDS)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    try:
        body = response.json()
    except Exception:
        body = response.text[:200]
    return response.status_code, elapsed_ms, body


def check_service_a(client: httpx.Client) -> bool:
    """Validate Service A's /health endpoint."""
    print(f"[Service A] {RETRIEVAL_SERVICE_URL}")
    status_code, elapsed_ms, body = timed_get(client, f"{RETRIEVAL_SERVICE_URL}/health")
    print(f"  GET /health  →  HTTP {status_code}  ({elapsed_ms} ms)")
    print(f"  Body: {body}")

    if status_code == 200 and isinstance(body, dict) and body.get("status") == "healthy":
        print("  ✓ Service A is healthy.
")
        return True

    print("  ✗ Service A health check failed.")
    print(
        "    → Check Cloud Run logs:
"
        "      gcloud run services logs read policy-retrieval --region=YOUR_REGION
"
        "    Common causes: RAG_CORPUS missing, Vertex AI API disabled, or service startup failed.
"
    )
    return False


def check_service_b(client: httpx.Client) -> bool:
    """Validate Service B's /health endpoint."""
    print(f"[Service B] {AGENT_SERVICE_URL}")
    status_code, elapsed_ms, body = timed_get(client, f"{AGENT_SERVICE_URL}/health")
    print(f"  GET /health  →  HTTP {status_code}  ({elapsed_ms} ms)")
    print(f"  Body: {body}")

    if status_code == 200 and isinstance(body, dict) and body.get("status") == "healthy":
        print("  ✓ Service B is healthy.
")
        return True

    print("  ✗ Service B health check failed.")
    print(
        "    → Check Cloud Run logs:
"
        "      gcloud run services logs read policy-agent --region=YOUR_REGION
"
        "    Common causes: RETRIEVAL_SERVICE_URL missing, AGENT_MODEL missing, or startup config validation failed.
"
    )
    return False


def run_end_to_end_test(client: httpx.Client) -> bool:
    """Run a live query through Service B and verify a non-empty answer."""
    print("[End-to-end test]")
    status_code, elapsed_ms, body = timed_post(
        client,
        f"{AGENT_SERVICE_URL}/query",
        {"query": TEST_QUERY},
    )
    print(f"  POST /query  →  HTTP {status_code}  ({elapsed_ms} ms)")
    print(f"  Query: "{TEST_QUERY}"")

    if status_code != 200 or not isinstance(body, dict):
        print(f"  Body: {body}")
        print("  ✗ End-to-end request failed.")
        print(
            "    → Verify that Service B can reach Service A and that the RAG corpus contains relevant documents."
        )
        return False

    answer = str(body.get("answer", "")).strip()
    context_count = body.get("context_count", 0)
    execution_path = body.get("execution_path", "N/A")

    print(f"  Answer (first 150 chars): "{answer[:150]}"")
    print(f"  Context count: {context_count}")
    print(f"  Execution path: {execution_path}")

    if answer and context_count:
        print("  ✓ End-to-end query succeeded.
")
        return True

    print("  ✗ End-to-end query returned an empty answer or zero contexts.")
    print(
        "    → Check that your RAG corpus is populated and that the query matches the content in your documents.
"
    )
    return False


def main() -> None:
    """Run all deployed-service checks and exit 0/1 for pass/fail."""
    require_url("RETRIEVAL_SERVICE_URL", RETRIEVAL_SERVICE_URL)
    require_url("AGENT_SERVICE_URL", AGENT_SERVICE_URL)

    with httpx.Client() as client:
        service_a_ok = check_service_a(client)
        service_b_ok = check_service_b(client)
        end_to_end_ok = False
        if service_a_ok and service_b_ok:
            end_to_end_ok = run_end_to_end_test(client)

    if service_a_ok and service_b_ok and end_to_end_ok:
        print("All checks passed. ✓")
        sys.exit(0)

    print("One or more checks failed. See remediation messages above.")
    sys.exit(1)


if __name__ == "__main__":
    main()
