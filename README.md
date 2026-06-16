# Chapter 10: From Local Triumph to Cloud Failure

**Part 4 of *From Local Triumph to Cloud Failure***

This repository is the companion code for Chapter 10. It shows why an agent
that appears correct on a laptop can fail in a stateless cloud deployment, and
how to fix that failure by moving retrieval out of process and into a dedicated
FastAPI service backed by Vertex AI RAG Engine.

---

## Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│                        test_client/query.py                       │
│                  Reader sends a live policy question              │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ POST /query
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ Service B: policy-agent                                           │
│ FastAPI + Google ADK agent                                        │
│ Cloud Run                                                         │
│ - Inline tool definitions                                         │
│ - Stateless request handling                                      │
│ - Calls Service A via httpx                                       │
│ - No direct Vertex AI RAG calls                                   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ POST /retrieve
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ Service A: policy-retrieval                                       │
│ FastAPI retrieval service                                         │
│ Cloud Run                                                         │
│ - Wraps Vertex AI RAG Engine                                      │
│ - Stable JSON API boundary                                        │
│ - No agent logic                                                  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ rag.retrieval_query()
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ Vertex AI RAG Engine                                              │
│ Durable external retrieval state                                  │
│ Shared by every Cloud Run worker                                  │
└────────────────────────────────────────────────────────────────────┘
```

The chapter's central idea is visible in the diagram: **Service A is the
persistence boundary**. The agent process in Service B stays stateless, while
all retrieval state lives in the external RAG-backed service.

---

## What the repo teaches

| Section | Teaching goal | Observable output |
|---|---|---|
| 10.1 | Show why in-process memory fails across stateless cloud requests | Two sequential requests report different `container_id` values and no shared cache hits |
| 10.2 | Show that concurrent workers do not share memory | Two concurrent requests print different workers and `shared_state: False` |
| 10.3 | Show the architectural fix | The fixed agent reports `cache_hit: N/A` and consistent retrieval through Service A |
| 10.4 | Introduce a dedicated FastAPI retrieval boundary | `/retrieve` returns structured JSON contexts from Vertex AI RAG Engine |
| 10.5 | Deploy a resilient cloud backend | `/health`, `/ready`, structured logs, and end-to-end validation all pass |

---

## Repository structure

```text
ch10-cloud-agent-patterns/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── validate_env.py
├── validate_gcp.py
├── validate_rag.py
├── validate_services.py
├── broken_agent/
│   ├── __init__.py
│   ├── stateful_agent.py
│   └── run_stateless_failure.py
├── fixed_agent/
│   ├── __init__.py
│   └── stateless_agent.py
├── retrieval_service/
│   ├── __init__.py
│   ├── app.py
│   ├── rag_client.py
│   └── Dockerfile
├── agent_service/
│   ├── __init__.py
│   ├── config.py
│   ├── agent_factory.py
│   ├── app.py
│   └── Dockerfile
├── test_client/
│   └── __init__.py
└── scripts/
    ├── deploy_service_a.sh
    └── deploy_service_b.sh
```

---

## Prerequisites

- Python 3.11 or later
- `uv` installed
- Docker installed
- `gcloud` CLI installed and authenticated
- A GCP project with billing enabled
- A Vertex AI RAG corpus containing at least one document

---

## GCP provisioning checklist

### 1. Enable required APIs

```bash
gcloud services enable   aiplatform.googleapis.com   run.googleapis.com   artifactregistry.googleapis.com   cloudresourcemanager.googleapis.com   --project=YOUR_PROJECT_ID
```

### 2. Create a service account

```bash
gcloud iam service-accounts create ch10-agent   --display-name="Chapter 10 Agent SA"   --project=YOUR_PROJECT_ID
```

### 3. Assign required IAM roles

These are the exact roles this chapter requires and why each one matters.

```bash
SA="ch10-agent@YOUR_PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID   --member="serviceAccount:$SA"   --role="roles/aiplatform.user"
# Needed by Service A to call Vertex AI RAG Engine.

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID   --member="serviceAccount:$SA"   --role="roles/run.invoker"
# Needed when one Cloud Run service calls another.

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID   --member="serviceAccount:$SA"   --role="roles/run.developer"
# Needed to deploy and update Cloud Run services.

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID   --member="serviceAccount:$SA"   --role="roles/artifactregistry.writer"
# Needed to push container images.
```

### 4. Create an Artifact Registry repository

```bash
gcloud artifacts repositories create ch10-images   --repository-format=docker   --location=us-central1   --project=YOUR_PROJECT_ID
```

### 5. Create and populate a Vertex AI RAG corpus

```bash
gcloud ai rag-corpora create   --display-name="company-policies"   --project=YOUR_PROJECT_ID   --region=us-central1
```

Use the returned corpus resource name in `RAG_CORPUS`, then ingest at least one document:

```bash
gcloud ai rag-files import   --corpus=projects/YOUR_PROJECT_ID/locations/us-central1/ragCorpora/YOUR_CORPUS_ID   --gcs-uris=gs://YOUR_BUCKET/policies.pdf   --project=YOUR_PROJECT_ID   --region=us-central1
```

### 6. Create a local service account key for development

```bash
gcloud iam service-accounts keys create sa-key.json   --iam-account="$SA"   --project=YOUR_PROJECT_ID
```

Set `GOOGLE_APPLICATION_CREDENTIALS` in your `.env` file to the absolute path
of this file.

---

## Local setup with uv

```bash
git clone https://github.com/mohitagr18/ch10-cloud-agent-patterns.git
cd ch10-cloud-agent-patterns
uv sync
cp .env.example .env
```

Edit `.env` and fill in every required value before running any scripts.

---

## Validate your setup

Run these scripts in order. They are reader-facing validation tools, not test
files. Each one checks one layer of the stack and exits with code 0 on success
or code 1 with a remediation message on failure.

### 1. Environment variables

```bash
uv run python validate_env.py
```

Expected success pattern:

```text
Checking required environment variables...
  GOOGLE_CLOUD_PROJECT     ✓  my-gcp-project-123
  GOOGLE_CLOUD_LOCATION    ✓  us-central1
  GOOGLE_APPLICATION_CREDENTIALS  ✓  /home/you/.config/gcloud/sa-key.json
  RAG_CORPUS               ✓  projects/my-project/locations/us-central1/ragCorpora/123456789
  AGENT_MODEL              ✓  gemini-2.0-flash-001

All required environment variables are present. ✓
```

### 2. GCP project and API access

```bash
uv run python validate_gcp.py
```

Expected success pattern:

```text
Checking GCP project access...
  Project: my-gcp-project-123  ✓  (My GCP Project)

Checking required API status...
  aiplatform.googleapis.com          ✓  ENABLED
  run.googleapis.com                 ✓  ENABLED
  artifactregistry.googleapis.com    ✓  ENABLED

GCP project and all required APIs verified. ✓
```

### 3. Vertex AI RAG corpus

```bash
uv run python validate_rag.py
```

Expected success pattern:

```text
Checking Vertex AI RAG corpus...
  Corpus:     projects/my-project/locations/us-central1/ragCorpora/123456789
  Test query: "What is this knowledge base about?"

  Contexts returned:  3
  Top result (first 100 chars):
    "This knowledge base contains company policies..."

RAG corpus is reachable and returning results. ✓
```

### 4. Deployed services

Run this only after both Cloud Run services are deployed and both URLs are set
in `.env`.

```bash
uv run python validate_services.py

You can also send a single live query with:

```bash
uv run python test_client/query.py
```
```

Expected success pattern:

```text
[Service A] https://policy-retrieval-xxxx-uc.a.run.app
  GET /health  →  HTTP 200  (142 ms)
  ✓ Service A is healthy.

[Service B] https://policy-agent-xxxx-uc.a.run.app
  GET /health  →  HTTP 200  (188 ms)
  ✓ Service B is healthy.

[End-to-end test]
  POST /query  →  HTTP 200  (1847 ms)
  Answer (first 150 chars): "Employees must submit expense reports within 30 days..."
  Context count: 3
  Execution path: adk_agent_inline_tool -> service_a_http -> grounded_answer
  ✓ End-to-end query succeeded.

All checks passed. ✓
```

---

## Run the chapter code

### Section 10.1 and 10.2 — The failure

Deploy the broken agent variant, then run:

```bash
uv run python broken_agent/run_stateless_failure.py
```

Expected output pattern:

```text
SECTION 10.1 — Sequential requests, in-process cache
  [Request 1] container_id : abc123
  [Request 1] cache_hits   : 0
  [Request 2] container_id : def456
  [Request 2] cache_hits   : 0

OBSERVATION: Requests landed on DIFFERENT container instances.
  Request 1 populated its cache, but Request 2 never saw it.
```

```text
SECTION 10.2 — Concurrent requests, memory loss guaranteed
  [Worker A] container_id : abc123
  [Worker A] cache_hits   : 0
  [Worker B] container_id : def456
  [Worker B] cache_hits   : 0

OBSERVATION:
  concurrent_requests : 2
  unique_containers   : 2
  shared_state        : False
```

### Section 10.3 — The fix

Run the fixed version against a live Service A:

```bash
uv run python fixed_agent/stateless_agent.py
```

Expected output pattern:

```text
SECTION 10.3 — Fixed stateless agent, two sequential calls
  status          : success
  context_count   : 5
  source_service  : https://policy-retrieval-xxxx-uc.a.run.app/retrieve
  cache_hits      : N/A — no in-process cache exists

OBSERVATION:
  Both requests returned consistent results.
  All retrieval went through Service A over HTTP.
```

### Section 10.4 — Run Service A locally

```bash
uv run uvicorn retrieval_service.app:app --host 0.0.0.0 --port 8080
```

In a second terminal:

```bash
curl -X POST http://localhost:8080/retrieve   -H "Content-Type: application/json"   -d '{"query": "What is the remote work policy?", "top_k": 5}'
```

Expected response pattern:

```json
{
  "query": "What is the remote work policy?",
  "contexts": [
    {
      "text": "Employees may work remotely up to three days per week...",
      "relevance_score": 0.91
    }
  ],
  "context_count": 1,
  "corpus": "projects/my-project/locations/us-central1/ragCorpora/123456789"
}
```

### Section 10.5 — Deploy the full stack

Deploy Service A first, then Service B.

```bash
bash scripts/deploy_service_a.sh
# Copy the resulting Cloud Run URL into RETRIEVAL_SERVICE_URL in .env

bash scripts/deploy_service_b.sh
# Copy the resulting Cloud Run URL into AGENT_SERVICE_URL in .env

uv run python validate_services.py

You can also send a single live query with:

```bash
uv run python test_client/query.py
```
```

---

## Troubleshooting

### 1. Pickle or serialisation failures when deploying tools

**Symptom:** a deployment fails with a pickle/import error involving tool
functions or module references.

**Cause:** the tool definition crossed a boundary that the runtime could not
serialize cleanly.

**Fix:** define tools inline in the agent factory. This repo does that in
`agent_service/agent_factory.py`, which is the same structural lesson proven in
the reference repo.

### 2. State appears to disappear across Cloud Run requests

**Symptom:** the local cache works on your laptop but not after deployment.

**Cause:** Cloud Run does not provide shared in-process memory across requests or
workers. Each worker has its own process and its own heap.

**Fix:** remove mutable in-process retrieval state and route every retrieval call
through Service A. Compare `broken_agent/stateful_agent.py` with
`fixed_agent/stateless_agent.py`.

### 3. Service B returns 500 or 502 after deployment

**Symptom:** `/health` works, but `/query` fails.

**Most common causes:**
- `RETRIEVAL_SERVICE_URL` is missing or malformed
- Service A is unhealthy
- `RAG_CORPUS` is wrong or the corpus is empty
- the service account is missing `roles/aiplatform.user`

**Fix path:**
1. `uv run python validate_services.py`
2. `gcloud run services logs read policy-retrieval --region=YOUR_REGION`
3. `gcloud run services logs read policy-agent --region=YOUR_REGION`
4. `uv run python validate_rag.py`

---

## Design notes for readers

A few choices in this repo are deliberately didactic.

- The broken and fixed agents are structurally similar so the retrieval change
  is easy to isolate.
- The agent backend returns contexts in the JSON response even though a
  production API might hide them. That makes grounding visible while learning.
- The final answer path is deterministic and grounded in retrieved context so
  readers can verify where the answer came from.
- `validate_*` scripts are treated as first-class artifacts because environment
  mistakes are the most common reason cloud demos fail in practice.

---

## Dependency management

This project uses **uv** as its only dependency manager.

- Initialize with `uv init`
- Add packages with `uv add`
- Run scripts with `uv run`
- Use `pyproject.toml` as the single source of truth

No `pip`, `poetry`, or `conda` workflow is used in this repository.
