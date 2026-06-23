# Setup Guide — Chapter 10: From Local Triumph to Cloud Failure

This guide walks through every step needed to provision GCP resources, upload your policy document to Vertex AI RAG Engine, deploy the Cloud Run services, and demonstrate the stateful cloud failure and its stateless fix.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| uv | latest | `pip install uv` |
| gcloud CLI | latest | [cloud.google.com/sdk](https://cloud.google.com/sdk) |
| Docker | latest | [docker.com](https://docker.com) |

GCP Requirements:
- A Google Cloud Platform project with billing enabled.
- Authenticated `gcloud` CLI matching your project.

---

## Step 1 — Clone and Install

Clone the repository and set up dependencies locally:

```bash
git clone https://github.com/mohitagr18/ch10-cloud-agent-patterns.git
cd ch10-cloud-agent-patterns
uv sync
```

---

## Step 2 — Configure GCP Project & Enable APIs

Set your Google Cloud project ID variable in your terminal and enable the required APIs:

```bash
# Set your project ID
export GOOGLE_CLOUD_PROJECT="your-project-id"
gcloud config set project $GOOGLE_CLOUD_PROJECT

# Enable all required APIs
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com
```

---

## Step 3 — Configure Local Credentials (ADC)

Generate Application Default Credentials (ADC) so local validation scripts can securely interact with Vertex AI services:

```bash
gcloud auth login
gcloud auth application-default login

# Print the ADC global configuration path to find your credentials JSON
gcloud info --format='value(config.paths.global_config_dir)'
```

On macOS/Linux, this is typically stored at:
`~/.config/gcloud/application_default_credentials.json`

---

## Step 4 — Build Infrastructure (Artifact Registry)

Create the Artifact Registry repository in `us-west1` to host the container images:

```bash
gcloud artifacts repositories create ch10-images \
  --repository-format docker \
  --location us-west1 \
  --project $GOOGLE_CLOUD_PROJECT

gcloud auth configure-docker us-west1-docker.pkg.dev
```

---

## Step 5 — Create a Vertex AI RAG Corpus

Initialize and create a RAG corpus in `us-west1` using the Vertex AI SDK:

```bash
uv run python - <<'EOF'
import os
import vertexai
from vertexai.preview import rag

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = "us-west1"

if not PROJECT_ID:
    print("Error: GOOGLE_CLOUD_PROJECT environment variable is not set.")
    exit(1)

vertexai.init(project=PROJECT_ID, location=LOCATION)

corpus = rag.create_corpus(display_name="company-policies")
print("\n=== RAG Corpus Created ===")
print("RAG_CORPUS =", corpus.name)
EOF
```

Copy the printed `RAG_CORPUS` resource name (e.g. `projects/<project-number>/locations/us-west1/ragCorpora/<corpus-id>`).

---

## Step 6 — Create GCS Bucket and Ingest Policies PDF

Create a Cloud Storage bucket, copy the document PDF into it, and ingest it into your Vertex AI RAG corpus:

```bash
# Generate a unique bucket name
export BUCKET_NAME="ch10-policies-$GOOGLE_CLOUD_PROJECT"

# Create the bucket
gsutil mb -p $GOOGLE_CLOUD_PROJECT -l us-west1 gs://$BUCKET_NAME/

# Upload the policies PDF
gsutil cp sunrise_healthcare_policies.pdf gs://$BUCKET_NAME/
```

Now import the file into the RAG corpus (ensure you set your `$RAG_CORPUS` environment variable beforehand):

```bash
# Set your RAG_CORPUS resource name from Step 5
export RAG_CORPUS="projects/<project-number>/locations/us-west1/ragCorpora/<corpus-id>"

uv run python - <<'EOF'
import os
import vertexai
from vertexai.preview import rag

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
RAG_CORPUS = os.getenv("RAG_CORPUS")
LOCATION = "us-west1"

if not PROJECT_ID or not RAG_CORPUS:
    print("Error: GOOGLE_CLOUD_PROJECT and RAG_CORPUS environment variables must be set.")
    exit(1)

BUCKET_NAME = f"ch10-policies-{PROJECT_ID}"
vertexai.init(project=PROJECT_ID, location=LOCATION)

response = rag.import_files(
    corpus_name=RAG_CORPUS,
    paths=[f"gs://{BUCKET_NAME}/sunrise_healthcare_policies.pdf"],
    chunk_size=512,
    chunk_overlap=100,
)
print("Import complete:", response)
EOF
```

---

## Step 7 — Configure Environment & Validate Setup

Copy the example `.env` template and populate the variables:

```bash
cp .env.example .env
```

Open `.env` and fill in the values:
```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-west1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/application_default_credentials.json
RAG_CORPUS=projects/YOUR_PROJECT_NUMBER/locations/us-west1/ragCorpora/YOUR_CORPUS_ID
AGENT_MODEL=gemini-2.0-flash-001
```

Validate your local environment to verify RAG engine query capabilities:
```bash
uv run python validate_env.py
uv run python validate_gcp.py
uv run python validate_rag.py
```

All three must print `PASS` before proceeding.

---

## Step 8 — Deploy Service A: policy-retrieval

Service A wraps Vertex AI RAG Engine and exposes a stateless `/retrieve` endpoint.

```bash
# Submit Cloud Build
gcloud builds submit \
  --tag us-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/ch10-images/policy-retrieval:latest \
  --project $GOOGLE_CLOUD_PROJECT \
  .

# Grant Vertex AI User roles to the Compute default service account used by Cloud Run
export PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")
export SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

# Deploy Service A to Cloud Run
gcloud run deploy policy-retrieval \
  --image us-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/ch10-images/policy-retrieval:latest \
  --region us-west1 \
  --project $GOOGLE_CLOUD_PROJECT \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 1 \
  --memory 512Mi \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-west1,RAG_CORPUS=$RAG_CORPUS
```

Retrieve the Service A URL and export it, then save it to `.env` as `RETRIEVAL_SERVICE_URL`:

```bash
export RETRIEVAL_SERVICE_URL=$(gcloud run services describe policy-retrieval --region us-west1 --project $GOOGLE_CLOUD_PROJECT --format="value(status.url)")
echo "RETRIEVAL_SERVICE_URL = $RETRIEVAL_SERVICE_URL"
```

Verify that it responds:
```bash
curl $RETRIEVAL_SERVICE_URL/health
# {"status": "healthy", "service": "policy-retrieval"}
```

---

## Step 9 — Deploy Service B (broken): policy-agent-broken

This variant demonstrates the statelessness failure. It features a module-level in-process dict cache. It is deployed with `--concurrency 1` and `--min-instances 2` so concurrent requests are forced to route to separate containers, exposing the memory-isolation bug.

```bash
# Submit Cloud Build for the broken agent
gcloud builds submit \
  --config cloudbuild_broken.yaml \
  --project $GOOGLE_CLOUD_PROJECT \
  .

# Deploy policy-agent-broken
gcloud run deploy policy-agent-broken \
  --image us-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/ch10-images/policy-agent-broken:latest \
  --region us-west1 \
  --project $GOOGLE_CLOUD_PROJECT \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 2 \
  --max-instances 10 \
  --concurrency 1 \
  --memory 512Mi \
  --timeout 120 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-west1,AGENT_MODEL=$AGENT_MODEL,RETRIEVAL_SERVICE_URL=$RETRIEVAL_SERVICE_URL
```

Retrieve the Service URL and export it, then save it to `.env` as `BROKEN_AGENT_URL`:

```bash
export BROKEN_AGENT_URL=$(gcloud run services describe policy-agent-broken --region us-west1 --project $GOOGLE_CLOUD_PROJECT --format="value(status.url)")
echo "BROKEN_AGENT_URL = $BROKEN_AGENT_URL"
```

---

## Step 10 — Run the Statelessness Failure Demonstration

Execute the fail demonstration script:

```bash
uv run python broken_agent/run_stateless_failure.py
```

### What to notice in the output:
- **Section 10.1 (Sequential requests)**: Requests land on different container instances (distinguished by a unique UUID suffix appended to the `container_id`). When they split, the second request shows `cache_hits: 0`.
- **Section 10.2 (Concurrent requests)**: The requests are sent simultaneously. Because `--concurrency 1` is configured, Cloud Run routes them to different instances. You will observe `unique_containers: 2` and `shared_state: False`, proving that in-process memory does not survive container boundaries in the cloud.

---

## Step 11 — Deploy Service B (fixed): policy-agent

This is the stateless architecture fix. It removes all in-process caching logic and delegates every retrieval query to Service A over HTTP.

```bash
# Submit Cloud Build for the fixed agent
gcloud builds submit \
  --tag us-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/ch10-images/policy-agent:latest \
  --project $GOOGLE_CLOUD_PROJECT \
  .

# Deploy policy-agent
gcloud run deploy policy-agent \
  --image us-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/ch10-images/policy-agent:latest \
  --region us-west1 \
  --project $GOOGLE_CLOUD_PROJECT \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 1 \
  --memory 512Mi \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-west1,AGENT_MODEL=$AGENT_MODEL,RETRIEVAL_SERVICE_URL=$RETRIEVAL_SERVICE_URL
```

Retrieve the Service URL and export it, then save it to `.env` as `AGENT_SERVICE_URL`:

```bash
export AGENT_SERVICE_URL=$(gcloud run services describe policy-agent --region us-west1 --project $GOOGLE_CLOUD_PROJECT --format="value(status.url)")
echo "AGENT_SERVICE_URL = $AGENT_SERVICE_URL"
```

---

## Step 12 — Validate Fixed Architecture & Run E2E Test

Run the validation suite end-to-end to verify that all deployed services are running, healthy, and communicating:

```bash
uv run python validate_services.py
```

You can also send a test query directly to the stateless agent backend:
```bash
uv run python test_client/query.py
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `unique_containers: 1` every run | Service still at default concurrency=80 | Redeploy with `--concurrency 1 --min-instances 2` |
| `cache_hits: "N/A"` on broken agent | Script pointing at fixed agent URL | Set `BROKEN_AGENT_URL` in `.env`; check that it takes precedence over `AGENT_SERVICE_URL` |
| `502` from policy-agent-broken | `RETRIEVAL_SERVICE_URL` not set on Cloud Run | Redeploy with `--set-env-vars` including `RETRIEVAL_SERVICE_URL` |
| `validate_services.py` fails | Service A or B not healthy | Run `curl <url>/health` on each service and check Cloud Run logs |
| Build fails: `COPY pyproject.toml` not found | Build context is wrong directory | Always run `gcloud builds submit` from the repo root, not from a subdirectory |
| `SyntaxError` in run_stateless_failure.py | Curly-quote corruption from editor | Ensure straight ASCII quotes are used in all scripts |

---

## Build Context Note

Both `cloudbuild.yaml` and `cloudbuild_broken.yaml` rely on the **repo root** as the Docker build context. The Dockerfiles inside each service subdirectory do:

```dockerfile
COPY pyproject.toml README.md ./
COPY broken_agent ./broken_agent
```

Always run builds from the repo root:

```bash
gcloud builds submit --config cloudbuild_broken.yaml .
```

Never run from inside `broken_agent/` or `agent_service/`.
