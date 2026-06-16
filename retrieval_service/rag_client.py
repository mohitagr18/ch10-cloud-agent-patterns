"""
retrieval_service/rag_client.py — Section 10.4

A thin wrapper around Vertex AI RAG Engine. This module exists so the FastAPI
app can stay focused on HTTP concerns while this file owns the retrieval call
shape, error handling, and response normalisation.

Why this matters for the chapter:
  Service A is the persistence boundary. Every Cloud Run worker that needs
  retrieval should call this service over HTTP rather than hold retrieval state
  in memory. By isolating the RAG call here, the reader can see exactly where
  the durable retrieval boundary lives.
"""

from __future__ import annotations

import os
from typing import Any

import vertexai
from vertexai.preview import rag


def initialise_vertex_ai() -> None:
    """Initialise Vertex AI using environment configuration.

    This is called once per process at startup. Cloud Run may create many
    processes over time, but each process performs the same deterministic
    initialisation using environment variables rather than local state.
    """
    vertexai.init(
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )


def retrieval_query(query_text: str, top_k: int = 5) -> dict[str, Any]:
    """Query the configured Vertex AI RAG corpus and return structured contexts.

    The raw Vertex AI response contains protobuf-like objects that are not ideal
    to return directly from a web API. This function normalises them into plain
    dictionaries so Service A can return stable JSON to any caller.

    Args:
        query_text: The natural-language question to send to the corpus.
        top_k: The maximum number of contexts to request.

    Returns:
        A dict containing the query, context list, context count, and corpus.

    Raises:
        ValueError: If RAG_CORPUS is missing.
        RuntimeError: If the underlying Vertex AI call fails.
    """
    rag_corpus = os.getenv("RAG_CORPUS")
    if not rag_corpus:
        raise ValueError(
            "RAG_CORPUS environment variable is not set. "
            "Expected format: projects/PROJECT_ID/locations/REGION/ragCorpora/CORPUS_ID"
        )

    try:
        rag_resource = rag.RagResource(rag_corpus=rag_corpus)
        response = rag.retrieval_query(
            rag_resources=[rag_resource],
            text=query_text,
            similarity_top_k=top_k,
        )

        contexts = []
        for context in response.contexts.contexts:
            contexts.append(
                {
                    "text": context.text,
                    "relevance_score": getattr(context, "distance", None),
                }
            )

        return {
            "query": query_text,
            "contexts": contexts,
            "context_count": len(contexts),
            "corpus": rag_corpus,
        }
    except Exception as exc:
        raise RuntimeError(
            f"Vertex AI RAG retrieval failed for corpus '{rag_corpus}'. "
            f"Check that the corpus exists, is populated, and that the service account "
            f"has roles/aiplatform.user. Underlying error: {exc}"
        ) from exc
