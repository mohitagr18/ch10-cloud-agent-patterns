"""
validate_gcp.py — GCP project and API readiness check for Chapter 10.

Confirms two things before you run any cloud code:
  1. Your credentials can reach the GCP project in GOOGLE_CLOUD_PROJECT.
  2. The three APIs this chapter depends on are enabled in that project.

A disabled API will produce a cryptic 403 deep inside the agent. This script
surfaces that failure up front with a direct remediation command.

Usage:
    uv run python validate_gcp.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# The three APIs the chapter requires and why each one matters.
REQUIRED_APIS: list[tuple[str, str]] = [
    (
        "aiplatform.googleapis.com",
        "Vertex AI — required for rag.retrieval_query() in Service A",
    ),
    (
        "run.googleapis.com",
        "Cloud Run — required to deploy and invoke both services",
    ),
    (
        "artifactregistry.googleapis.com",
        "Artifact Registry — required to store container images for deployment",
    ),
]


def check_project_access(project_id: str) -> tuple[bool, str]:
    """Attempt to fetch the GCP project resource to confirm credentials are valid.

    Returns (success, display_name_or_error_message). Fetching the project
    resource is the lightest possible API call that still exercises the full
    credential chain: ADC → token fetch → IAM check.
    """
    try:
        from google.cloud import resourcemanager_v3

        client = resourcemanager_v3.ProjectsClient()
        project = client.get_project(name=f"projects/{project_id}")
        display_name = project.display_name or project_id
        return True, display_name
    except Exception as exc:
        return False, str(exc)


def check_api_status(project_id: str, api_name: str) -> tuple[bool, str]:
    """Return (is_enabled, status_string) for a single GCP API.

    Uses the Service Usage API, which is always enabled and does not need
    to be in REQUIRED_APIS itself. A disabled API returns state DISABLED;
    an enabled one returns ENABLED.
    """
    try:
        from google.cloud import service_usage_v1

        client = service_usage_v1.ServiceUsageClient()
        service_resource = f"projects/{project_id}/services/{api_name}"
        service = client.get_service(name=service_resource)

        # State 2 == ENABLED in the protobuf enum
        is_enabled = service.state.value == 2
        state_label = "ENABLED" if is_enabled else "DISABLED"
        return is_enabled, state_label
    except Exception as exc:
        return False, f"ERROR — {exc}"


def main() -> None:
    """Run all GCP checks and exit with an appropriate code."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        print(
            "GOOGLE_CLOUD_PROJECT is not set.\n"
            "Run validate_env.py first to check all required variables."
        )
        sys.exit(1)

    # ── Project access ────────────────────────────────────────────────────────
    print("Checking GCP project access...")
    print()
    success, display_name_or_error = check_project_access(project_id)

    if success:
        print(f"  Project: {project_id}  ✓  ({display_name_or_error})")
    else:
        print(f"  Project: {project_id}  ✗  UNREACHABLE")
        print(f"    Error: {display_name_or_error}")
        print()
        print(
            "  Possible causes:\n"
            "  • GOOGLE_APPLICATION_CREDENTIALS points to a missing or invalid key file\n"
            "  • The service account does not have resourcemanager.projects.get permission\n"
            "  • The project ID is wrong — check GOOGLE_CLOUD_PROJECT in your .env"
        )
        sys.exit(1)

    # ── API status ────────────────────────────────────────────────────────────
    print()
    print("Checking required API status...")
    print()

    disabled_apis: list[str] = []
    for api_name, reason in REQUIRED_APIS:
        is_enabled, state_label = check_api_status(project_id, api_name)
        status_icon = "✓" if is_enabled else "✗"
        print(f"  {api_name:<45} {status_icon}  {state_label}")
        if not is_enabled:
            print(f"    Purpose: {reason}")
            print(
                f"    → Enable it with:\n"
                f"      gcloud services enable {api_name} --project={project_id}"
            )
            print()
            disabled_apis.append(api_name)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if not disabled_apis:
        print("GCP project and all required APIs verified. ✓")
        sys.exit(0)
    else:
        count = len(disabled_apis)
        print(
            f"{count} API(s) disabled. Enable them with the commands above and re-run."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
