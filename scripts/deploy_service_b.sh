#!/usr/bin/env bash
set -euo pipefail

# deploy_service_b.sh — Deploy the ADK agent backend to Cloud Run.
#
# Why this script matters for the chapter:
#   The deployment command is where stateless architecture becomes real. Service
#   B discovers Service A through RETRIEVAL_SERVICE_URL injected at deploy time.
#   No hardcoded URLs exist in the codebase.

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env or your shell.}"
: "${GOOGLE_CLOUD_LOCATION:?Set GOOGLE_CLOUD_LOCATION in .env or your shell.}"
: "${AGENT_MODEL:?Set AGENT_MODEL in .env or your shell.}"
: "${RETRIEVAL_SERVICE_URL:?Set RETRIEVAL_SERVICE_URL in .env or your shell.}"

SERVICE_NAME="policy-agent"
IMAGE_URI="${GOOGLE_CLOUD_LOCATION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/ch10-images/${SERVICE_NAME}:latest"

printf '
Deploying %s to Cloud Run...
' "$SERVICE_NAME"
printf 'Project:               %s
' "$GOOGLE_CLOUD_PROJECT"
printf 'Region:                %s
' "$GOOGLE_CLOUD_LOCATION"
printf 'Image URI:             %s
' "$IMAGE_URI"
printf 'Retrieval service URL: %s

' "$RETRIEVAL_SERVICE_URL"

gcloud builds submit   --project "$GOOGLE_CLOUD_PROJECT"   --tag "$IMAGE_URI"   .

gcloud run deploy "$SERVICE_NAME"   --project "$GOOGLE_CLOUD_PROJECT"   --region "$GOOGLE_CLOUD_LOCATION"   --image "$IMAGE_URI"   --platform managed   --allow-unauthenticated   --port 8080   --memory 1Gi   --cpu 1   --set-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION,AGENT_MODEL=$AGENT_MODEL,RETRIEVAL_SERVICE_URL=$RETRIEVAL_SERVICE_URL"

printf '
Service B deployed. Fetch its URL with:
'
printf 'gcloud run services describe %s --region %s --format="value(status.url)"
' "$SERVICE_NAME" "$GOOGLE_CLOUD_LOCATION"
