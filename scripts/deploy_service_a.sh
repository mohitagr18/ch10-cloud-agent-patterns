#!/usr/bin/env bash
set -euo pipefail

# deploy_service_a.sh — Deploy the FastAPI retrieval service to Cloud Run.
#
# Why this script matters for the chapter:
#   Readers should not have to reverse-engineer a long gcloud command from the
#   prose. This script turns the deployment pattern into a concrete artifact
#   they can inspect, edit, and run.

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env or your shell.}"
: "${GOOGLE_CLOUD_LOCATION:?Set GOOGLE_CLOUD_LOCATION in .env or your shell.}"
: "${RAG_CORPUS:?Set RAG_CORPUS in .env or your shell.}"

SERVICE_NAME="policy-retrieval"
IMAGE_URI="${GOOGLE_CLOUD_LOCATION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/ch10-images/${SERVICE_NAME}:latest"

printf '
Deploying %s to Cloud Run...
' "$SERVICE_NAME"
printf 'Project:   %s
' "$GOOGLE_CLOUD_PROJECT"
printf 'Region:    %s
' "$GOOGLE_CLOUD_LOCATION"
printf 'Image URI: %s
' "$IMAGE_URI"
printf 'RAG corpus:%s

' "$RAG_CORPUS"

gcloud builds submit   --project "$GOOGLE_CLOUD_PROJECT"   --tag "$IMAGE_URI"   .

gcloud run deploy "$SERVICE_NAME"   --project "$GOOGLE_CLOUD_PROJECT"   --region "$GOOGLE_CLOUD_LOCATION"   --image "$IMAGE_URI"   --platform managed   --allow-unauthenticated   --port 8080   --memory 1Gi   --cpu 1   --set-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION,RAG_CORPUS=$RAG_CORPUS"

printf '
Service A deployed. Fetch its URL with:
'
printf 'gcloud run services describe %s --region %s --format="value(status.url)"
' "$SERVICE_NAME" "$GOOGLE_CLOUD_LOCATION"
