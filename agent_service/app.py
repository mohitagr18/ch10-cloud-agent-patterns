"""
agent_service/app.py — Section 10.5

FastAPI wrapper around the ADK agent. This service exposes a small HTTP API so
Cloud Run can host the agent as a normal stateless backend. All retrieval state
lives outside this process in Service A.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from agent_service.agent_factory import (
    compose_grounded_answer,
    create_agent,
    run_retrieval_step,
)
from agent_service.config import AgentServiceConfig, load_config

logger = structlog.get_logger("agent_service")
config: AgentServiceConfig | None = None
agent = None


class QueryRequest(BaseModel):
    """Request body for the agent query endpoint.

    The request includes the full user question so the backend remains fully
    stateless. No session history is stored in process memory.
    """

    query: str = Field(..., min_length=1, description="User policy question")


class QueryResponse(BaseModel):
    """Structured JSON response from the agent backend."""

    answer: str
    contexts: list[dict[str, Any]]
    context_count: int
    retrieval_service_url: str
    container_id: str
    cache_hits: str
    execution_path: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise configuration and the ADK agent at startup.

    Process-level setup belongs here because it is deterministic and does not
    depend on any individual request. That is very different from storing
    mutable retrieval state in memory between requests.
    """
    global config, agent
    config = load_config()
    agent = create_agent(config)
    logger.info(
        "agent_service_startup",
        service=config.service_name,
        version=config.service_version,
        project=config.google_cloud_project,
        location=config.google_cloud_location,
        retrieval_service_url=config.retrieval_service_url,
        model=config.agent_model,
    )
    yield
    logger.info("agent_service_shutdown", service=config.service_name)


app = FastAPI(title="policy-agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Emit structured logs for every incoming request."""
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
    """Return a simple machine-readable health response."""
    service_name = config.service_name if config else "policy-agent"
    service_version = config.service_version if config else "1.0.0"
    return {
        "status": "healthy",
        "service": service_name,
        "version": service_version,
    }


@app.get("/ready")
def readiness() -> dict[str, str]:
    """Return a readiness response distinct from health."""
    if config is None or agent is None:
        raise HTTPException(status_code=503, detail="Agent service not initialised yet.")
    return {"status": "ready"}


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest) -> dict[str, Any]:
    """Process a user question through the agent's explicit retrieval path.

    The service constructs a real ADK agent instance at startup. For request
    execution, it invokes the retrieval step explicitly, then composes a
    deterministic grounded answer from the returned contexts. This keeps the
    architecture transparent for readers while still showing the real ADK
    integration point and inline tool pattern.
    """
    if config is None or agent is None:
        raise HTTPException(status_code=503, detail="Agent service is not ready.")

    try:
        retrieval_result = run_retrieval_step(agent, payload.query)

        if retrieval_result.get("status") == "error":
            raise HTTPException(status_code=502, detail=retrieval_result["error_message"])

        contexts = retrieval_result.get("contexts", [])
        answer = compose_grounded_answer(payload.query, retrieval_result)
        container_id = os.getenv("K_REVISION", "local-dev-container")

        logger.info(
            "agent_query_complete",
            query=payload.query,
            context_count=len(contexts),
            retrieval_service_url=config.retrieval_service_url,
            container_id=container_id,
            execution_path="adk_agent_inline_tool -> service_a_http -> grounded_answer",
        )

        return {
            "answer": answer,
            "contexts": contexts,
            "context_count": len(contexts),
            "retrieval_service_url": config.retrieval_service_url,
            "container_id": container_id,
            "cache_hits": "N/A — stateless agent; no in-process cache exists",
            "execution_path": "adk_agent_inline_tool -> service_a_http -> grounded_answer",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Unexpected agent backend failure. Check RETRIEVAL_SERVICE_URL, AGENT_MODEL, "
                f"and Cloud Run logs. Underlying error: {exc}"
            ),
        ) from exc
