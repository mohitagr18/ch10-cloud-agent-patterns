"""
retrieval_service/app.py — Section 10.4

FastAPI service that wraps Vertex AI RAG Engine behind a stable HTTP boundary.
Every agent worker calls this service instead of querying RAG directly. That is
what makes the architecture resilient: retrieval state lives outside the agent
process entirely.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from retrieval_service.rag_client import initialise_vertex_ai, retrieval_query

logger = structlog.get_logger("retrieval_service")
SERVICE_NAME = "policy-retrieval"
SERVICE_VERSION = "1.0.0"


class RetrieveRequest(BaseModel):
    """Request body for /retrieve.

    The request is intentionally small and explicit. Readers should see that a
    stateless service accepts all required input in the request itself rather
    than relying on session memory.
    """

    query: str = Field(..., min_length=1, description="Policy question to retrieve against")
    top_k: int = Field(5, ge=1, le=10, description="Maximum number of contexts to return")


class RetrieveResponse(BaseModel):
    """Structured JSON response for /retrieve.

    Returning JSON rather than raw SDK objects makes the service predictable for
    both human readers and downstream clients like Service B.
    """

    query: str
    contexts: list[dict[str, Any]]
    context_count: int
    corpus: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise SDK state on startup and log clean shutdown on exit.

    Cloud Run instances are ephemeral. Startup and shutdown hooks show readers
    where to place process-level concerns like SDK initialisation without
    smuggling request state into module globals.
    """
    initialise_vertex_ai()
    logger.info(
        "retrieval_service_startup",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        rag_corpus=os.getenv("RAG_CORPUS"),
    )
    yield
    logger.info("retrieval_service_shutdown", service=SERVICE_NAME)


app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION, lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Emit structured logs for every request.

    The chapter teaches observability as part of resilience. Structured request
    logs make it easy to correlate a user query in Service B with the retrieval
    request it triggered in Service A.
    """
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
    """Return a Cloud Run health response.

    Cloud Run health checks should be boring and machine-readable. A stable JSON
    shape lets validate_services.py check health deterministically.
    """
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest) -> dict[str, Any]:
    """Retrieve contexts from Vertex AI RAG Engine for a policy query.

    This endpoint is the service boundary the chapter introduces. Any agent
    worker can call it over HTTP and get the same result regardless of which
    process handled the request.
    """
    try:
        result = retrieval_query(payload.query, payload.top_k)
        logger.info(
            "rag_retrieval_complete",
            query=payload.query,
            top_k=payload.top_k,
            context_count=result["context_count"],
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
