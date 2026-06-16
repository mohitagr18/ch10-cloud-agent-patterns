# Chapter 10: From Local Triumph to Cloud Failure

**Part 4 of *Building Production AI Agents* by Mohit Aggarwal**

This repository is the companion code for Chapter 10. It demonstrates why a
stateful agent that runs perfectly on a laptop will fail in a stateless cloud
environment — and how to fix it with a two-service architecture on Cloud Run.

---

## What you will build

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client (test_client/query.py)           │
└───────────────────────────────┬─────────────────────────────────┘
                                │ POST /query
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Service B — policy-agent  (agent_service/)                     │
│  Google ADK agent, stateless                                    │
│  Cloud Run · FastAPI · uvicorn                                  │
│  Tools call Service A over HTTP — no local RAG state            │
└───────────────────────────────┬─────────────────────────────────┘
                                │ POST /retrieve
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Service A — policy-retrieval  (retrieval_service/)             │
│  FastAPI wrapper around Vertex AI RAG Engine                    │
│  Cloud Run · stateless · independently scalable                 │
└───────────────────────────────┬─────────────────────────────────┘
                                │ rag.retrieval_query()
                                ▼
                    ┌───────────────────────┐
                    │  Vertex AI RAG Engine │
                    │  (your corpus)        │
                    └───────────────────────┘
```

Service A is the **persistence boundary**. It holds no agent state — it simply
wraps the RAG corpus and returns contexts over HTTP. Service B holds no
retrieval state — it simply runs the ADK agent and delegates every lookup to
Service A. Neither service cares how many container instances Cloud Run starts.

---

## Chapter sections

| Section | What the code shows |
|---------|---------------------|
| 10.1 | Stateful agent fails on Cloud Run — in-process cache disappears across requests |
| 10.2 | Concurrent requests hit different workers — memory loss made visible in the terminal |
| 10.3 | Before/after comparison — broken cache vs. stateless httpx call |
| 10.4 | FastAPI retrieval service wrapping Vertex AI RAG Engine |
| 10.5 | Full deployment, health checks, structured logging, end-to-end test |

---

## Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) installed (`pip install uv` or see uv docs)
- A GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- Docker (for building container images locally before pushing)

---

## GCP provisioning checklist

Complete these steps before running any code. The validation scripts will
confirm each one.

### 1. Enable required APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=YOUR_PROJECT_ID
```

### 2. Create a service account

```bash
gcloud iam service-accounts create ch10-agent \
  --display-name="Chapter 10 Agent SA" \
  --project=YOUR_PROJECT_ID
```

### 3. Assign required IAM roles

```bash
SA="ch10-agent@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# Vertex AI — needed by Service A to call rag.retrieval_query()
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/aiplatform.user"

# Cloud Run — needed to call Service A from Service B with an identity token
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/run.invoker"

# Cloud Run — needed to deploy both services
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/run.developer"

# Artifact Registry — needed to push Docker images
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/artifactregistry.writer"
```

### 4. Create an Artifact Registry repository

```bash
gcloud artifacts repositories create ch10-images \
  --repository-format=docker \
  --location=us-central1 \
  --project=YOUR_PROJECT_ID
```

### 5. Create a Vertex AI RAG corpus and ingest documents

```bash
# Create the corpus
gcloud ai rag-corpora create \
  --display-name="company-policies" \
  --project=YOUR_PROJECT_ID \
  --region=us-central1

# Note the numeric ID in the output — you will use it for RAG_CORPUS.
# Ingest a document (replace with your GCS bucket path or Drive URL)
gcloud ai rag-files import \
  --corpus=YOUR_CORPUS_RESOURCE_NAME \
  --gcs-uris=gs://YOUR_BUCKET/policies.pdf \
  --project=YOUR_PROJECT_ID \
  --region=us-central1
```

### 6. Download a local service account key (for development only)

```bash
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=$SA \
  --project=YOUR_PROJECT_ID
# Set GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/sa-key.json in .env
```

---

## Local setup with uv

```bash
# Clone the repo
git clone https://github.com/mohitagr18/ch10-cloud-agent-patterns
cd ch10-cloud-agent-patterns

# Install all dependencies
uv sync

# Copy and fill in your environment variables
cp .env.example .env
# Edit .env with your project ID, region, RAG corpus, etc.
```

---

## Validate your setup

Run these four scripts **in order** before running any chapter code.
Each script checks one layer of the stack and exits with code 0 on success
or code 1 with a specific remediation message on failure.

### Step 1 — Environment variables

```bash
uv run python validate_env.py
```

Expected output (all values present):
```
Checking required environment variables...

  GOOGLE_CLOUD_PROJECT     ✓  my-gcp-project-123
  GOOGLE_CLOUD_LOCATION    ✓  us-central1
  GOOGLE_APPLICATION_CREDENTIALS  ✓  /home/you/.config/gcloud/sa-key.json
  RAG_CORPUS               ✓  projects/my-project/locations/us-central1/ragCorpora/123...
  AGENT_MODEL              ✓  gemini-2.0-flash-001

All required environment variables are present. ✓
```

### Step 2 — GCP project and API access

```bash
uv run python validate_gcp.py
```

Expected output:
```
Checking GCP project access...
  Project: my-gcp-project-123  ✓  (My GCP Project)

Checking required API status...
  aiplatform.googleapis.com          ✓  ENABLED
  run.googleapis.com                 ✓  ENABLED
  artifactregistry.googleapis.com    ✓  ENABLED

GCP project and all required APIs verified. ✓
```

### Step 3 — Vertex AI RAG corpus

```bash
uv run python validate_rag.py
```

Expected output:
```
Checking Vertex AI RAG corpus...
  Corpus: projects/my-project/.../ragCorpora/123456789
  Test query: "What is this knowledge base about?"
  Contexts returned: 3
  Top result (first 100 chars): "This knowledge base contains company policies..."

RAG corpus is reachable and returning results. ✓
```

### Step 4 — Deployed Cloud Run services (run after Milestone F)

```bash
uv run python validate_services.py
```

Expected output:
```
[Service A] https://policy-retrieval-xxxx-uc.a.run.app
  GET /health  →  HTTP 200  (142 ms)  {"status": "healthy"}  ✓

[Service B] https://policy-agent-xxxx-uc.a.run.app
  GET /health  →  HTTP 200  (188 ms)  {"status": "healthy"}  ✓

[End-to-end test]
  POST /query  →  HTTP 200  (1847 ms)
  Answer: "Employees must submit expense reports within 30 days..."  ✓

All checks passed. ✓
```

---

## Run the chapter code

> Complete all four validation steps above before running these.

### Section 10.1 and 10.2 — Statelessness failure

```bash
# Deploy the broken agent first (see scripts/deploy_service_a.sh and deploy_service_b.sh)
uv run python broken_agent/run_stateless_failure.py
```

### Section 10.3 — The fix

```bash
uv run python fixed_agent/stateless_agent.py
```

### Section 10.4 — FastAPI retrieval service (local test)

```bash
uv run uvicorn retrieval_service.app:app --reload --port 8080
# In a second terminal:
curl -X POST http://localhost:8080/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the remote work policy?", "top_k": 5}'
```

### Section 10.5 — Full deployment

```bash
bash scripts/deploy_service_a.sh
bash scripts/deploy_service_b.sh
uv run python test_client/query.py
```

---

## Troubleshooting

### "PicklingError" or "cannot pickle" when deploying the agent

The agent tools must be defined **inside** the agent factory function, not at
module level. Any tool defined at module scope captures a module reference
that cannot be serialized. See `agent_service/agent_factory.py` for the
correct pattern. This is the same failure the reference repo resolved and
the chapter discusses in Section 10.3.

### "RAG_CORPUS not configured" at runtime on Cloud Run

Cloud Run services do not read your local `.env` file. Environment variables
must be passed at deploy time with `--set-env-vars`. Check that
`scripts/deploy_service_a.sh` includes `--set-env-vars RAG_CORPUS=...`
and that the value matches your `.env` file exactly.

### Service B returns 500 after deployment

The most common cause is `RETRIEVAL_SERVICE_URL` not being set on Service B,
which means Service B cannot reach Service A. Verify the value:
```bash
gcloud run services describe policy-agent \
  --region=us-central1 --format="value(spec.template.spec.containers[0].env)"
```
If `RETRIEVAL_SERVICE_URL` is missing or wrong, redeploy with the correct
`--set-env-vars` flag (see `scripts/deploy_service_b.sh`).

---

## Repository structure

```
ch10-cloud-agent-patterns/
├── validate_env.py          # Step 1: checks all env vars
├── validate_gcp.py          # Step 2: confirms GCP access and API status
├── validate_rag.py          # Step 3: tests RAG corpus with a live query
├── validate_services.py     # Step 4: end-to-end health check after deployment
├── broken_agent/
│   ├── stateful_agent.py    # 10.1 — agent with in-process cache (the failure)
│   └── run_stateless_failure.py  # 10.1/10.2 — sends requests to Cloud Run; shows memory loss
├── fixed_agent/
│   └── stateless_agent.py   # 10.3 — same agent, cache removed, calls Service A
├── retrieval_service/
│   ├── app.py               # 10.4 — FastAPI service wrapping Vertex AI RAG
│   ├── rag_client.py        # 10.4 — rag.retrieval_query() wrapper
│   └── Dockerfile
├── agent_service/
│   ├── app.py               # 10.5 — FastAPI wrapper for the ADK agent
│   ├── agent_factory.py     # 10.5 — ADK agent with inline tool definitions
│   ├── config.py            # 10.5 — env var validation at startup
│   └── Dockerfile
├── test_client/
│   └── query.py             # simple test client for the deployed agent
├── scripts/
│   ├── deploy_service_a.sh  # gcloud run deploy for Service A
│   └── deploy_service_b.sh  # gcloud run deploy for Service B
├── pyproject.toml
├── .env.example
└── .gitignore
```
