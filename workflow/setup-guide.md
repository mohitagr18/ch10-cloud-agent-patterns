# Chapter 10 Cloud Setup: Vertex AI RAG + Cloud Run (Step‑by‑Step)

This guide walks a reader from a **fresh Google Cloud project** to a fully working deployment of:

- Service A: `policy-retrieval` (FastAPI + Vertex AI RAG Engine)
- Service B: `policy-agent` (FastAPI + ADK agent calling Service A over HTTP)
- End‑to‑end validation using `validate_*` scripts

All commands are copy‑pasteable and assume macOS or Linux with `zsh`/`bash`.

---

## 0. Before you start

### Create a Google Cloud account (free credits)

If you don’t already have one, create a **Google Cloud Platform (GCP)** account:

- Go to <https://cloud.google.com>
- Sign up with your Google account  
- Create a **new project** and **enable billing**

Google typically provides **free trial credits** for new accounts. Use those credits for this chapter’s exercises so you can experiment without incurring out‑of‑pocket costs. Check the current free tier and credit details in the Cloud Console billing section.

Make a note of:

- **Project ID** (e.g. `project-a44fece1-48df-4c9b-ac9`)
- **Project number** (e.g. `946002739647`)

You will need both.

### Local prerequisites

Install:

- Python 3.11+
- Docker
- `gcloud` CLI: <https://cloud.google.com/sdk/docs/install>
- `uv` (Python dependency manager): <https://github.com/astral-sh/uv>

Authenticate `gcloud`:

```bash
gcloud auth login
gcloud auth application-default login
```

Set your project:

```bash
gcloud config set project PROJECT_ID
```

Replace `PROJECT_ID` with your actual project ID.

---

## 1. Clone the repo and set up `uv`

```bash
git clone https://github.com/mohitagr18/ch10-cloud-agent-patterns.git
cd ch10-cloud-agent-patterns

# Create and sync virtualenv + dependencies
uv sync

# Create your env file
cp .env.example .env
```

You’ll fill `.env` in step 4.

---

## 2. Enable required GCP APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  --project=PROJECT_ID
```

---

## 3. Configure local credentials (ADC)

We’ll use **Application Default Credentials** instead of JSON keys, which is both simpler and recommended for local development.

```bash
gcloud auth application-default login

# Find where ADC is stored
gcloud info --format='value(config.paths.global_config_dir)'
```

Your ADC path will be:

```text
/Users/you/.config/gcloud/application_default_credentials.json
```

Add this path to `.env` (step 4).

---

## 4. Fill in `.env`

Open `.env` and set:

```env
GOOGLE_CLOUD_PROJECT=PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-west1
GOOGLE_APPLICATION_CREDENTIALS=/Users/you/.config/gcloud/application_default_credentials.json

RAG_CORPUS=projects/PROJECT_NUMBER/locations/us-west1/ragCorpora/CORPUS_ID   # fill later

RETRIEVAL_SERVICE_URL=
AGENT_SERVICE_URL=

AGENT_MODEL=gemini-2.0-flash-001
```

You will fill `RAG_CORPUS`, `RETRIEVAL_SERVICE_URL`, and `AGENT_SERVICE_URL` after you create the RAG corpus and deploy both Cloud Run services.

---

## 5. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create ch10-images \
  --repository-format=docker \
  --location=us-west1 \
  --project=PROJECT_ID
```

This is where your container images will be pushed.

---

## 6. Create a Vertex AI RAG corpus in `us-west1`

The `gcloud ai rag-corpora` command is not available in every CLI version, so use the Python SDK via `uv`.

```bash
cd ~/Documents/GitHub/ch10-cloud-agent-patterns  # adjust path if needed

uv run python - <<'EOF'
import vertexai
from vertexai.preview import rag

PROJECT_ID = "PROJECT_ID"
LOCATION = "us-west1"

vertexai.init(project=PROJECT_ID, location=LOCATION)

corpus = rag.create_corpus(display_name="company-policies")
print("RAG_CORPUS =", corpus.name)
EOF
```

This prints a corpus resource name, e.g.:

```text
RAG_CORPUS = projects/946002739647/locations/us-west1/ragCorpora/2305843009213693952
```

Copy that full string into `.env` as `RAG_CORPUS`, and confirm `GOOGLE_CLOUD_LOCATION=us-west1`.

---

## 7. Create a GCS bucket and upload your policies PDF

Create a bucket in the same region:

```bash
gsutil mb -p PROJECT_ID -l us-west1 gs://ch10-policies-YOURNAME/
```

Upload a policy PDF (you can use the one you generated for this chapter, or any text‑based PDF):

```bash
gsutil cp /path/to/sunrise_healthcare_policies.pdf gs://ch10-policies-YOURNAME/
```

---

## 8. Ingest the PDF into the RAG corpus

Use the Vertex AI RAG Python SDK:

```bash
uv run python - <<'EOF'
import vertexai
from vertexai.preview import rag

PROJECT_ID = "PROJECT_ID"
LOCATION = "us-west1"
CORPUS_NAME = "projects/946002739647/locations/us-west1/ragCorpora/2305843009213693952"

vertexai.init(project=PROJECT_ID, location=LOCATION)

response = rag.import_files(
    corpus_name=CORPUS_NAME,
    paths=["gs://ch10-policies-YOURNAME/sunrise_healthcare_policies.pdf"],
    chunk_size=512,
    chunk_overlap=100,
)

print("Import complete:", response)
EOF
```

You should see `imported_rag_files_count: 1` in the output.

---

## 9. Validate environment and GCP setup

Run the validation scripts in order:

```bash
# Check .env is complete and consistent
uv run python validate_env.py

# Verify project + APIs
uv run python validate_gcp.py

# Verify RAG corpus is reachable and returns contexts
uv run python validate_rag.py
```

All three should exit with success messages.

---

## 10. Build and deploy Service A (policy‑retrieval)

### 10.1. Create `cloudbuild.yaml` for Service A

From the repo root:

```bash
cd ~/Documents/GitHub/ch10-cloud-agent-patterns

cat > cloudbuild_service_a.yaml <<'EOF'
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'us-west1-docker.pkg.dev/project-a44fece1-48df-4c9b-ac9/ch10-images/policy-retrieval:latest'
      - '-f'
      - 'retrieval_service/Dockerfile'
      - '.'
images:
  - 'us-west1-docker.pkg.dev/project-a44fece1-48df-4c9b-ac9/ch10-images/policy-retrieval:latest'
EOF
```

Replace `project-a44fece1-48df-4c9b-ac9` with your `PROJECT_ID`.

### 10.2. Build the image

```bash
gcloud builds submit --project PROJECT_ID \
  --config cloudbuild_service_a.yaml \
  .
```

You should see `STATUS  SUCCESS` at the end.

### 10.3. Grant Vertex AI roles to the Cloud Run service account

Cloud Build uses the **Compute default service account** by default for Cloud Run:

```bash
SA_EMAIL="946002739647-compute@developer.gserviceaccount.com"  # replace PROJECT_NUMBER

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

# (Optional but convenient for a demo)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.admin"
```

### 10.4. Deploy Service A to Cloud Run

```bash
gcloud run deploy policy-retrieval \
  --project=PROJECT_ID \
  --region=us-west1 \
  --image=us-west1-docker.pkg.dev/PROJECT_ID/ch10-images/policy-retrieval:latest \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars=\
GOOGLE_CLOUD_PROJECT=PROJECT_ID,\
GOOGLE_CLOUD_LOCATION=us-west1,\
RAG_CORPUS=projects/PROJECT_NUMBER/locations/us-west1/ragCorpora/CORPUS_ID
```

Note:

- Use your **actual** `PROJECT_ID`, `PROJECT_NUMBER`, and `CORPUS_ID`.
- We pass project, location, and corpus as environment variables so the service is fully self‑contained.

After the deploy finishes, note the **Service URL**, e.g.:

```text
https://policy-retrieval-946002739647.us-west1.run.app
```

Set this in `.env`:

```env
RETRIEVAL_SERVICE_URL=https://policy-retrieval-946002739647.us-west1.run.app
```

---

## 11. Sanity‑check Service A (`/health` and `/retrieve`)

Health check:

```bash
curl -s -S https://policy-retrieval-...us-west1.run.app/health | python -m json.tool
```

You should see:

```json
{
  "status": "healthy",
  "service": "policy-retrieval",
  "version": "1.0.0"
}
```

RAG retrieval check:

```bash
curl -s -S -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the expense reimbursement policy?"}' \
  https://policy-retrieval-...us-west1.run.app/retrieve | python -m json.tool
```

Expected: a JSON response with `contexts` that mention mileage, reimbursement, expense policy, etc.

If you see a **permission error** mentioning `aiplatform.ragCorpora.get`, double‑check:

- The service account mapped to `policy-retrieval` has `roles/aiplatform.user` (or admin).
- `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` are set to your project and `us-west1`.
- `retrieval_service/rag_client.py` calls `vertexai.init(project=..., location=...)` using those env vars.

---

## 12. Build and deploy the Broken Agent Service (policy-agent-broken)

To demonstrate why in-process state fails across stateless cloud requests (Sections 10.1 and 10.2), build and deploy the broken agent variant.

### 12.1. Update `cloudbuild_broken.yaml`
Open `cloudbuild_broken.yaml` and replace the placeholder project ID `project-a44fece1-48df-4c9b-ac9` with your actual `PROJECT_ID`:

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'us-west1-docker.pkg.dev/PROJECT_ID/ch10-images/policy-agent-broken:latest'
      - '-f'
      - 'broken_agent/Dockerfile'
      - '.'
images:
  - 'us-west1-docker.pkg.dev/PROJECT_ID/ch10-images/policy-agent-broken:latest'
```

### 12.2. Build the image
From the repo root:

```bash
gcloud builds submit --project PROJECT_ID \
  --config cloudbuild_broken.yaml \
  .
```

### 12.3. Deploy the Broken Agent to Cloud Run
Deploy the broken agent service and inject the required environment variables:

```bash
gcloud run deploy policy-agent-broken \
  --project=PROJECT_ID \
  --region=us-west1 \
  --image=us-west1-docker.pkg.dev/PROJECT_ID/ch10-images/policy-agent-broken:latest \
  --platform=managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars=\
GOOGLE_CLOUD_PROJECT=PROJECT_ID,\
GOOGLE_CLOUD_LOCATION=us-west1,\
AGENT_MODEL=gemini-2.0-flash-001,\
RETRIEVAL_SERVICE_URL=https://policy-retrieval-...us-west1.run.app
```

Replace `RETRIEVAL_SERVICE_URL` with the exact Service A URL from step 10.

After deployment, note the Service URL and update your `.env` file with `BROKEN_AGENT_URL`:

```env
BROKEN_AGENT_URL=https://policy-agent-broken-...us-west1.run.app
```

---

## 13. Run the stateless failure demonstration (Section 10.1 & 10.2)

Now run the demonstration script:

```bash
uv run python broken_agent/run_stateless_failure.py
```

### What to notice in the output:
- **Section 10.1 (Sequential Requests)**: If the requests land on different container instances, the second request will show `cache_hits: 0`.
- **Section 10.2 (Concurrent Requests)**: The concurrent requests are routed to different container instances, leading to `shared_state: False` and `unique_containers: 2`, illustrating that in-process state is not shared across stateless containers in the cloud.

---

## 14. Build and deploy Service B (policy‑agent)

### 14.1. Ensure Service B uses env vars

`agent_service/config.py` reads:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`
- `AGENT_MODEL`
- `RETRIEVAL_SERVICE_URL`

Confirm there are no hard‑coded regions or project IDs.

### 14.2. Create `cloudbuild.yaml` for Service B

From the repo root:

```bash
cat > cloudbuild_service_b.yaml <<'EOF'
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'us-west1-docker.pkg.dev/project-a44fece1-48df-4c9b-ac9/ch10-images/policy-agent:latest'
      - '-f'
      - 'agent_service/Dockerfile'
      - '.'
images:
  - 'us-west1-docker.pkg.dev/project-a44fece1-48df-4c9b-ac9/ch10-images/policy-agent:latest'
EOF
```

Replace `project-a44fece1-48df-4c9b-ac9` with your `PROJECT_ID`.

### 14.3. Build the image

```bash
gcloud builds submit --project PROJECT_ID \
  --config cloudbuild_service_b.yaml \
  .
```

### 14.4. Deploy Service B to Cloud Run

```bash
gcloud run deploy policy-agent \
  --project=PROJECT_ID \
  --region=us-west1 \
  --image=us-west1-docker.pkg.dev/PROJECT_ID/ch10-images/policy-agent:latest \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars=\
GOOGLE_CLOUD_PROJECT=PROJECT_ID,\
GOOGLE_CLOUD_LOCATION=us-west1,\
AGENT_MODEL=gemini-2.0-flash-001,\
RETRIEVAL_SERVICE_URL=https://policy-retrieval-...us-west1.run.app
```

Replace `RETRIEVAL_SERVICE_URL` with the exact Service A URL from step 10.

After deployment, get the Service B URL:

```bash
gcloud run services describe policy-agent \
  --region=us-west1 \
  --format="value(status.url)"
```

Set it in `.env`:

```env
AGENT_SERVICE_URL=https://policy-agent-...us-west1.run.app
```

---

## 15. Final validation (`validate_services.py`)

From the repo root:

```bash
uv run python validate_services.py
```

Expected success pattern:

```text
[Service A] https://policy-retrieval-...us-west1.run.app
  GET /health  →  HTTP 200 (...)
  Body: {'status': 'healthy', 'service': 'policy-retrieval', 'version': '1.0.0'}
  ✓ Service A is healthy.

[Service B] https://policy-agent-...us-west1.run.app
  GET /health  →  HTTP 200 (...)
  Body: {'status': 'healthy', 'service': 'policy-agent', 'version': '1.0.0'}
  ✓ Service B is healthy.

[End-to-end test]
  POST /query  →  HTTP 200 (...)
  Query: "What is the expense reimbursement policy?"
  Answer (first 150 chars): "…"
  Context count: 3
  Execution path: adk_agent_inline_tool -> service_a_http -> grounded_answer
  ✓ End-to-end query succeeded.

All checks passed. ✓
```

At this point, the chapter’s architecture is fully live:

- Service B (agent) is stateless and calls Service A over HTTP.
- Service A encapsulates all retrieval using Vertex AI RAG Engine.
- RAG state is durable and shared across Cloud Run workers.

---

## 16. Optional: direct test queries against the agent

You can hit the deployed agent directly:

```bash
curl -s -S -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "Summarize the timekeeping policy for clinicians."}' \
  https://policy-agent-...us-west1.run.app/query | python -m json.tool
```

Or use the included test client:

```bash
uv run python test_client/query.py
```

---

## 17. Summary of key ideas for readers

- **Free credits** on Google Cloud make it feasible to run this chapter end‑to‑end without long‑term cost.
- **Service A** is the **persistence boundary**: all retrieval state lives in a managed RAG Engine, not in‑process caches.
- **Service B** remains stateless, relying on HTTP calls to Service A and can scale horizontally on Cloud Run without memory sharing issues.
- The `validate_*` scripts are deliberately first‑class artifacts: they catch exactly the kinds of subtle misconfigurations (project IDs, regions, IAM gaps) that routinely sink cloud demos.

