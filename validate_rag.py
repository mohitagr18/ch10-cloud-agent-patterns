"""
validate_rag.py — Vertex AI RAG corpus reachability check for Chapter 10.

Sends a single test query to the corpus specified in RAG_CORPUS and prints
the number of contexts returned plus the first 100 characters of the top
result. If the corpus is empty or unreachable, you will see the exact error
and the resource name that was attempted — not a traceback buried in the
agent.

This script uses the same rag.retrieval_query() call pattern as the
production code in retrieval_service/rag_client.py. If this script passes,
the production path will work.

Usage:
    uv run python validate_rag.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# A neutral query that any company-policy corpus should be able to answer.
# It does not need to match your actual documents — it just needs to produce
# at least one context to confirm the corpus is populated and reachable.
TEST_QUERY = "What is this knowledge base about?"
TOP_K = 3


def initialise_vertex_ai(project_id: str, location: str) -> None:
    """Initialise the Vertex AI SDK with project and region.

    This must be called before any rag.* calls. The SDK reads credentials
    from GOOGLE_APPLICATION_CREDENTIALS (local) or the attached service
    account (Cloud Run).
    """
    import vertexai
    vertexai.init(project=project_id, location=location)


def query_rag_corpus(corpus_resource_name: str, query: str, top_k: int) -> dict:
    """Send a retrieval query to the corpus and return a structured result dict.

    Returns a dict with keys:
      success (bool), context_count (int), top_result (str), error (str|None)

    Keeping the return type as a plain dict (rather than raising exceptions)
    lets the caller print a clean diagnostic message rather than a raw traceback.
    """
    try:
        from vertexai.preview import rag

        rag_resource = rag.RagResource(rag_corpus=corpus_resource_name)
        response = rag.retrieval_query(
            rag_resources=[rag_resource],
            text=query,
            similarity_top_k=top_k,
        )

        contexts = response.contexts.contexts
        if not contexts:
            return {
                "success": False,
                "context_count": 0,
                "top_result": "",
                "error": (
                    "Query succeeded but returned zero contexts. "
                    "The corpus may be empty or the documents may not yet be indexed."
                ),
            }

        top_text = contexts[0].text if contexts else ""
        return {
            "success": True,
            "context_count": len(contexts),
            "top_result": top_text[:100],
            "error": None,
        }

    except Exception as exc:
        return {
            "success": False,
            "context_count": 0,
            "top_result": "",
            "error": str(exc),
        }


def main() -> None:
    """Run the RAG corpus check and exit with an appropriate code."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    corpus_resource_name = os.getenv("RAG_CORPUS")

    missing = [v for v in ["GOOGLE_CLOUD_PROJECT", "RAG_CORPUS"] if not os.getenv(v)]
    if missing:
        print(
            f"Missing required variables: {', '.join(missing)}\n"
            "Run validate_env.py first."
        )
        sys.exit(1)

    print("Checking Vertex AI RAG corpus...")
    print()
    print(f"  Corpus:     {corpus_resource_name}")
    print(f"  Test query: \"{TEST_QUERY}\"")
    print()

    # Initialise SDK before querying — this establishes the project context
    # that all subsequent rag.* calls inherit.
    try:
        initialise_vertex_ai(project_id, location)
    except Exception as exc:
        print(f"  Vertex AI init failed: {exc}")
        print(
            "  → Check that GOOGLE_APPLICATION_CREDENTIALS points to a valid key file\n"
            "    and that aiplatform.googleapis.com is enabled in your project."
        )
        sys.exit(1)

    result = query_rag_corpus(corpus_resource_name, TEST_QUERY, TOP_K)

    if result["success"]:
        print(f"  Contexts returned:  {result['context_count']}")
        print(f"  Top result (first 100 chars):")
        print(f"    "{result['top_result']}..."")
        print()
        print("RAG corpus is reachable and returning results. ✓")
        sys.exit(0)
    else:
        print(f"  Contexts returned:  0")
        print(f"  Error: {result['error']}")
        print()
        print(
            "  → Verify RAG_CORPUS in your .env file.\n"
            "    Expected format:\n"
            "      projects/PROJECT_ID/locations/REGION/ragCorpora/CORPUS_ID\n"
            "    List your corpora:\n"
            "      gcloud ai rag-corpora list --project=YOUR_PROJECT --region=YOUR_REGION\n"
            "    If the corpus exists but is empty, ingest at least one document:\n"
            "      gcloud ai rag-files import --corpus=CORPUS_NAME --gcs-uris=gs://YOUR_BUCKET/doc.pdf"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
