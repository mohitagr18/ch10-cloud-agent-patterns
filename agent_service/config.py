"""
agent_service/config.py — Section 10.5

Centralised environment loading and validation for Service B. The agent backend
should fail fast at startup when required configuration is missing, rather than
starting successfully and failing later on the first user request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass(frozen=True)
class AgentServiceConfig:
    """Typed configuration for the Cloud Run agent backend.

    A dataclass makes the configuration explicit and discoverable. The chapter
    teaches that cloud robustness starts with configuration that is validated at
    process startup rather than discovered accidentally during a request.
    """

    google_cloud_project: str
    google_cloud_location: str
    agent_model: str
    retrieval_service_url: str
    service_name: str = "policy-agent"
    service_version: str = "1.0.0"


def load_config() -> AgentServiceConfig:
    """Load and validate all required environment variables for Service B.

    Returns:
        A validated AgentServiceConfig instance.

    Raises:
        ValueError: If any required variable is missing or malformed.
    """
    google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    google_cloud_location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip()
    agent_model = os.getenv("AGENT_MODEL", "").strip()
    retrieval_service_url = os.getenv("RETRIEVAL_SERVICE_URL", "").rstrip("/").strip()

    missing_vars: list[str] = []
    if not google_cloud_project:
        missing_vars.append("GOOGLE_CLOUD_PROJECT")
    if not agent_model:
        missing_vars.append("AGENT_MODEL")
    if not retrieval_service_url:
        missing_vars.append("RETRIEVAL_SERVICE_URL")

    if missing_vars:
        missing_list = ", ".join(missing_vars)
        raise ValueError(
            f"Missing required environment variable(s): {missing_list}. "
            "Set them in your .env file for local runs or pass them with "
            "--set-env-vars during Cloud Run deployment."
        )

    if not retrieval_service_url.startswith("http://") and not retrieval_service_url.startswith("https://"):
        raise ValueError(
            "RETRIEVAL_SERVICE_URL must start with http:// or https://. "
            f"Received: {retrieval_service_url}"
        )

    return AgentServiceConfig(
        google_cloud_project=google_cloud_project,
        google_cloud_location=google_cloud_location,
        agent_model=agent_model,
        retrieval_service_url=retrieval_service_url,
    )
