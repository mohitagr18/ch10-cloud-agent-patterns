"""
broken_agent/app.py — Section 10.1 FastAPI wrapper

FastAPI wrapper around the stateful agent. Exposes the same HTTP interface as
agent_service/app.py. Retrieval is delegated to Service A over HTTP (same as
the fixed agent). The broken part is the module-level _retrieval_cache in
stateful_agent.py — this wrapper reads/writes it directly so cache_hits shows
the real integer count, never "N/A".
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from broken_agent import stateful_agent

logger = structlog.get_logger("policy-agent-broken")

# Generate a unique container instance/process ID at startup
INSTANCE_ID = f"{os.getenv('K_REVISION', 'local-dev-container')}-{uuid.uuid4().hex[:6]}"


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User policy question")


class QueryResponse(BaseModel):
    answer: str
    contexts: list[dict[str, Any]]
    context_count: int
    retrieval_service_url: str
    container_id: str
    cache_hits: str
    execution_path: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "policy_agent_broken_startup",
        retrieval_service_url=os.getenv("RETRIEVAL_SERVICE_URL", "NOT SET"),
    )
    yield
    logger.info("policy_agent_broken_shutdown")


app = FastAPI(title="policy-agent-broken", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "http_request_complete",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        return response
    except Exception:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.exception(
            "http_request_failed",
            method=request.method,
            path=request.url.path,
            elapsed_ms=elapsed_ms,
        )
        raise


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "policy-agent-broken", "version": "1.0.0"}


@app.get("/ready")
def readiness() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest) -> dict[str, Any]:
    """Run the query through the stateful (broken) agent.

    Retrieval is delegated to Service A over HTTP — same call pattern as the
    fixed agent. The only broken part is the module-level _retrieval_cache that
    cannot survive Cloud Run container boundaries.
    """
    retrieval_service_url = os.getenv("RETRIEVAL_SERVICE_URL", "").rstrip("/")
    if not retrieval_service_url:
        raise HTTPException(
            status_code=500,
            detail="RETRIEVAL_SERVICE_URL is not configured.",
        )

    # Step 1: call Service A for retrieval over HTTP
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{retrieval_service_url}/retrieve",
                json={"query": payload.query},
            )
            resp.raise_for_status()
            retrieval_data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Service A returned HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach retrieval service: {exc}",
        ) from exc

    contexts: list[dict] = retrieval_data.get("contexts", [])      # Simulate realistic processing time so concurrent requests land on separate     # container instances when concurrency=1 is set on the Cloud Run service.     # Without this delay the requests complete before the autoscaler can split them.     time.sleep(2)

    # Step 2: check/update the module-level in-process cache (the anti-pattern).
    # This cache works perfectly locally but silently fails in the cloud because
    # each container instance has its own empty copy of _retrieval_cache.
    if payload.query in stateful_agent._retrieval_cache:
        stateful_agent._cache_hit_count += 1
    else:
        stateful_agent._retrieval_cache[payload.query] = contexts

    cache_hits_count: int = stateful_agent._cache_hit_count

    # Step 3: compose a plain grounded answer from retrieved contexts
    if contexts:
        snippet = contexts[0].get("text", "")[:300]
        answer = (
            f"Based on company policy: {snippet}"
            if snippet
            else "Policy information retrieved but no text available."
        )
    else:
        answer = "No relevant policy context was found for your query."

    container_id = INSTANCE_ID

    logger.info(
        "broken_agent_query_complete",
        query=payload.query,
        context_count=len(contexts),
        cache_hits=cache_hits_count,
        container_id=container_id,
    )

    return {
        "answer": answer,
        "contexts": contexts,
        "context_count": len(contexts),
        "retrieval_service_url": retrieval_service_url,
        "container_id": container_id,
        "cache_hits": str(cache_hits_count),
        "execution_path": "stateful_cache_check -> service_a_http -> grounded_answer",
    }
