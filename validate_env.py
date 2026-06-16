"""
validate_env.py — Environment variable checker for Chapter 10.

Run this before any other script to confirm your .env file is complete.
Every missing variable will surface here with a specific remediation message
rather than as a cryptic runtime error inside the agent.

Usage:
    uv run python validate_env.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root so this script is runnable from any directory.
project_root = Path(__file__).parent
dotenv_path = project_root / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    print(
        "  WARNING: No .env file found at project root.\n"
        "  Copy .env.example to .env and fill in your values:\n"
        "    cp .env.example .env"
    )
    print()


# Each entry is (variable_name, is_secret, remediation_message).
# is_secret=True means we print only the first 4 characters.
REQUIRED_VARS: list[tuple[str, bool, str]] = [
    (
        "GOOGLE_CLOUD_PROJECT",
        False,
        "Set this to your GCP project ID (not the display name).\n"
        "      Find it at: https://console.cloud.google.com/home/dashboard",
    ),
    (
        "GOOGLE_CLOUD_LOCATION",
        False,
        "Set this to the GCP region containing your Vertex AI RAG corpus.\n"
        "      Example: us-central1",
    ),
    (
        "GOOGLE_APPLICATION_CREDENTIALS",
        False,
        "Set this to the absolute path of your GCP service account JSON key.\n"
        "      Example: /home/you/.config/gcloud/sa-key.json\n"
        "      Create a key at: https://console.cloud.google.com/iam-admin/serviceaccounts",
    ),
    (
        "RAG_CORPUS",
        False,
        "Set this to the full resource name of your Vertex AI RAG corpus.\n"
        "      Format: projects/PROJECT_ID/locations/REGION/ragCorpora/CORPUS_ID\n"
        "      List your corpora: gcloud ai rag-corpora list --project=YOUR_PROJECT --region=REGION",
    ),
    (
        "AGENT_MODEL",
        False,
        "Set this to the Gemini model ID for the agent.\n"
        "      Example: gemini-2.0-flash-001",
    ),
]

# These two are optional until the Cloud Run services are deployed.
# We check for them but do not fail if they are absent — we just warn.
OPTIONAL_POST_DEPLOY_VARS: list[tuple[str, str]] = [
    (
        "RETRIEVAL_SERVICE_URL",
        "Populated after deploying Service A. Required for validate_services.py.",
    ),
    (
        "AGENT_SERVICE_URL",
        "Populated after deploying Service B. Required for validate_services.py.",
    ),
]


def mask_secret(value: str) -> str:
    """Return the first 4 characters of a secret value followed by asterisks.

    Showing 4 characters lets the reader confirm the right credential was
    picked up without exposing the full value in terminal output.
    """
    if len(value) <= 4:
        return "****"
    return value[:4] + "****"


def check_required_vars() -> int:
    """Check all required variables and print a pass/fail line for each.

    Returns the number of missing variables so the caller can set the exit code.
    """
    missing_count = 0

    print("Checking required environment variables...")
    print()

    for var_name, is_secret, remediation in REQUIRED_VARS:
        value = os.getenv(var_name)

        if value:
            display_value = mask_secret(value) if is_secret else value
            print(f"  {var_name:<40} ✓  {display_value}")
        else:
            missing_count += 1
            print(f"  {var_name:<40} ✗  NOT SET")
            print(f"    → {remediation}")
            print()

    return missing_count


def check_optional_vars() -> None:
    """Check post-deployment variables and print a warning if absent.

    These are not required until Cloud Run services are deployed, so
    a missing value is a warning, not a failure.
    """
    print()
    print("Checking optional post-deployment variables...")
    print()

    for var_name, note in OPTIONAL_POST_DEPLOY_VARS:
        value = os.getenv(var_name)

        if value:
            print(f"  {var_name:<40} ✓  {value}")
        else:
            print(f"  {var_name:<40} —  not yet set")
            print(f"    ({note})")


def main() -> None:
    """Entry point: run all checks and exit with an appropriate code."""
    missing_count = check_required_vars()
    check_optional_vars()

    print()
    if missing_count == 0:
        print("All required environment variables are present. ✓")
        sys.exit(0)
    else:
        print(
            f"{missing_count} variable(s) missing. "
            "Set them in your .env file and re-run this script."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
