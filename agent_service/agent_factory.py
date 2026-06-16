"""
agent_service/agent_factory.py — Sections 10.4 and 10.5

Creates the Google ADK agent used by Service B. The tools are defined inline,
which avoids the pickle/import boundary failures documented in the reference
repo. More importantly for this chapter, every retrieval call goes to Service A
via httpx. The agent process never talks to Vertex AI RAG Engine directly.
"""

from __future__ import annotations

import httpx
from google.adk.agents import Agent

from agent_service.config import AgentServiceConfig


def create_agent(config: AgentServiceConfig) -> Agent:
    """Create a stateless enterprise policy assistant.

    The key teaching point is not the prompt, which is intentionally simple.
    The key point is where the tool sends its retrieval request: to Service A,
    the external persistence boundary, rather than to local in-process state.
    """

    def retrieve_policy_context(query: str) -> dict:
        """Call Service A's /retrieve endpoint over HTTP.

        This inline definition matters for two reasons:
          1. It avoids serialisation problems that can occur when tools are
             defined elsewhere and imported across deployment boundaries.
          2. It keeps the retrieval path stateless. Every invocation includes
             all required input in the request body.
        """
        retrieve_url = f"{config.retrieval_service_url}/retrieve"
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
                "source_service": retrieve_url,
            }
        except httpx.HTTPStatusError as exc:
            return {
                "status": "error",
                "error_message": (
                    f"Retrieval service returned HTTP {exc.response.status_code}. "
                    f"Check that RETRIEVAL_SERVICE_URL points to a healthy Cloud Run service. "
                    f"URL attempted: {retrieve_url}"
                ),
            }
        except httpx.ConnectError:
            return {
                "status": "error",
                "error_message": (
                    f"Could not connect to retrieval service at {retrieve_url}. "
                    "Check RETRIEVAL_SERVICE_URL in your environment and verify that "
                    "Service A is deployed and reachable."
                ),
            }
        except Exception as exc:
            return {
                "status": "error",
                "error_message": (
                    f"Unexpected retrieval failure while calling {retrieve_url}: {exc}"
                ),
            }

    return Agent(
        name="policy_assistant",
        model=config.agent_model,
        description="Enterprise policy assistant that retrieves context from Service A",
        instruction=(
            "You are an enterprise documentation assistant. "
            "When a user asks about company policy, call retrieve_policy_context to get "
            "relevant policy excerpts, then answer clearly and directly. "
            "If the tool returns an error or no contexts, say so plainly instead of guessing. "
            "Use the retrieved context as your grounding source."
        ),
        tools=[retrieve_policy_context],
    )


def run_retrieval_step(agent: Agent, query: str) -> dict:
    """Execute the retrieval step that the ADK agent would use during a query.

    This helper makes the execution path explicit for chapter readers. The
    service still constructs a real ADK Agent instance, but the request handler
    invokes the grounded retrieval step directly so the flow is deterministic,
    transparent, and easy to inspect in terminal output.

    Why this matters for the chapter:
      The chapter is teaching a cloud deployment pattern, not agent-framework
      internals. This helper keeps the runtime observable without hiding the
      critical architectural point behind opaque ADK orchestration details.

    Args:
        agent: The configured ADK agent instance.
        query: The user question.

    Returns:
        The dict produced by the inline retrieve_policy_context tool.
    """
    tool_function = agent.tools[0]
    return tool_function(query)


def compose_grounded_answer(query: str, retrieval_result: dict) -> str:
    """Build a deterministic grounded answer from retrieved contexts.

    A full production agent might let the model synthesize the final answer.
    For this chapter repo, we keep the answer path deterministic so readers can
    see that the response came from external retrieval rather than hidden local
    memory. That makes the statelessness lesson easier to verify.
    """
    if retrieval_result.get("status") == "error":
        return retrieval_result.get("error_message", "Retrieval failed.")

    contexts = retrieval_result.get("contexts", [])
    if not contexts:
        return (
            f"No policy context was returned for the question: {query}. "
            "Check whether your RAG corpus contains relevant documents."
        )

    top_context = contexts[0].get("text", "")
    return top_context if top_context else "A context was returned, but it was empty."
