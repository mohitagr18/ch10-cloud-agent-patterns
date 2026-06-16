"""
broken_agent/stateful_agent.py — Section 10.1

This module deliberately implements the anti-pattern: an agent that stores
retrieval results in a module-level dictionary. Locally, this cache works
exactly as intended — repeated queries return instantly from memory.

The problem only appears in the cloud. Cloud Run may route each request to a
different container instance. Each instance has its own process, its own heap,
and therefore its own empty cache. The cache never fills up across requests
because the requests never share a process.

This file is the "before" state. Read it alongside stateless_agent.py to see
what changes and why.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── The anti-pattern: module-level mutable state ──────────────────────────────
#
# This dict lives in the process heap. Any code in this module that runs in
# the same Python process will see the same dict. That is fine locally.
# On Cloud Run, each container instance is a separate process — so each
# instance has its own empty _retrieval_cache. There is no shared memory
# between instances, no matter how many requests the same service handles.
_retrieval_cache: dict[str, list[dict]] = {}
_cache_hit_count: int = 0


def retrieve_policy_context(query: str) -> dict:
    """Retrieve company policy contexts for a given query.

    On the first call with a given query, fetches from Vertex AI RAG Engine
    and stores the result in _retrieval_cache. On subsequent calls with the
    same query IN THE SAME PROCESS, returns the cached result.

    This caching logic is invisible to Cloud Run's load balancer. The balancer
    routes requests across instances with no awareness of what any instance has
    cached. The result: a cache that works perfectly in unit tests and local
    runs, and silently fails in production.

    Args:
        query: The user's policy question.

    Returns:
        A dict with keys: status, contexts, cache_hit, cache_size.
        cache_hit and cache_size are diagnostic fields that make the
        statelessness failure visible in the terminal output.
    """
    global _cache_hit_count

    # Check the in-process cache before going to Vertex AI.
    if query in _retrieval_cache:
        _cache_hit_count += 1
        return {
            "status": "success",
            "contexts": _retrieval_cache[query],
            "cache_hit": True,
            "cache_size": len(_retrieval_cache),
            "cache_hits_this_session": _cache_hit_count,
        }

    # Cache miss — fetch from Vertex AI RAG Engine.
    rag_corpus = os.getenv("RAG_CORPUS")
    if not rag_corpus:
        return {
            "status": "error",
            "error_message": (
                "RAG_CORPUS environment variable is not set. "
                "Check your .env file or Cloud Run service configuration."
            ),
        }

    try:
        import vertexai
        from vertexai.preview import rag

        vertexai.init(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )

        rag_resource = rag.RagResource(rag_corpus=rag_corpus)
        response = rag.retrieval_query(
            rag_resources=[rag_resource],
            text=query,
            similarity_top_k=5,
        )

        contexts = [
            {
                "text": ctx.text,
                "relevance_score": ctx.distance if hasattr(ctx, "distance") else None,
            }
            for ctx in response.contexts.contexts
        ]

        # Store in the in-process cache — useless across container boundaries.
        _retrieval_cache[query] = contexts

        return {
            "status": "success",
            "contexts": contexts,
            "cache_hit": False,
            "cache_size": len(_retrieval_cache),
            "cache_hits_this_session": _cache_hit_count,
        }

    except Exception as exc:
        return {
            "status": "error",
            "error_message": f"RAG retrieval failed: {exc}",
        }


def create_stateful_agent():
    """Create an ADK agent that uses the in-process cache for retrieval.

    The agent itself is straightforward. The problem is entirely in the
    retrieve_policy_context tool above: it relies on module-level state
    that cannot survive a process boundary.

    Returns:
        A configured google.adk.agents.Agent instance.
    """
    from google.adk.agents import Agent

    # Tools are defined inline to avoid pickle serialisation failures —
    # a lesson learned from the reference repo. The cache bug is separate
    # from the serialisation bug: both must be fixed, but in different ways.
    agent = Agent(
        name="stateful_policy_assistant",
        model=os.getenv("AGENT_MODEL", "gemini-2.0-flash-001"),
        description="Company policy assistant (broken: uses in-process cache)",
        instruction=(
            "You are an enterprise knowledge base assistant. "
            "When a user asks about company policy, use the retrieve_policy_context "
            "tool to find relevant information, then answer clearly and concisely. "
            "Always base your answer on the retrieved contexts, not on general knowledge."
        ),
        tools=[retrieve_policy_context],
    )
    return agent
