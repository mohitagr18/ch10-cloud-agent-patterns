# Setup Guide — Chapter 10: From Local Triumph to Cloud Failure

This guide walks through every step needed to reproduce the full chapter demo: local validation, deploying all three Cloud Run services, and running the statelessness failure demonstration.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| uv | latest | `pip install uv` |
| gcloud CLI | latest | [cloud.google.com/sdk](https://cloud.google.com/sdk) |
| Docker | latest | [docker.com](https://docker.com) |

GCP requirements:
- A GCP project with billing enabled
- Vertex AI API enabled
- Artifact Registry API enabled
- Cloud Run API enabled
- A service account with `roles/aiplatform.user` and `roles/aiplatform.admin`

---

## Step 1 — Clone and install

```bash
git clone https://github.com/mohitagr18/ch10-cloud-agent-patterns.git
cd ch10-cloud-agent-patterns
uv sync
```

---

## Step 2 — Configure environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Required variables in `.env`:

```
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-west1
AGENT_MODEL=gemini-2.0-flash-001
RAG_CORPUS=projects/<project-number>/locations/us-west1/ragCorpora/<corpus-id>
RETRIEVAL_SERVICE_URL=   # filled after Step 5
AGENT_SERVICE_URL=       # filled after Step 6
BROKEN_AGENT_URL=        # filled after Step 7
```

Validate your local environment:

```bash
uv run python validate_env.py
uv run python validate_gcp.py
uv run python validate_rag.py
```

All three should print `PASS` before proceeding.

---

## Step 3 — Build infrastructure (Artifact Registry)

Create the Artifact Registry repository if it does not already exist:

```bash
gcloud artifacts repositories create ch10-images \
  --repository-format docker \
  --location us-west1 \
  --project $GOOGLE_CLOUD_PROJECT

gcloud auth configure-docker us-west1-docker.pkg.dev
```

---

## Step 4 — Deploy Service A: policy-retrieval

Service A wraps Vertex AI RAG Engine and exposes a `/retrieve` endpoint.

```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --project $GOOGLE_CLOUD_PROJECT \
  .

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

Copy the Service URL into `.env` as `RETRIEVAL_SERVICE_URL`.

Verify:
```bash
curl $RETRIEVAL_SERVICE_URL/health
# {"status": "healthy", "service": "policy-retrieval"}
```

---

## Step 5 — Deploy Service B (fixed): policy-agent

Service B is the stateless fixed agent that calls Service A over HTTP.

```bash
gcloud run deploy policy-agent \
  --image us-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/ch10-images/policy-agent:latest \
  --region us-west1 \
  --project $GOOGLE_CLOUD_PROJECT \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 1 \
  --memory 512Mi \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-west1,RETRIEVAL_SERVICE_URL=$RETRIEVAL_SERVICE_URL
```

Copy the Service URL into `.env` as `AGENT_SERVICE_URL`.

Verify:
```bash
curl $AGENT_SERVICE_URL/health
# {"status": "healthy", "service": "policy-agent"}
```

Run full end-to-end validation:
```bash
uv run python validate_services.py
```

---

## Step 6 — Deploy Service B (broken): policy-agent-broken

This service is identical in interface to `policy-agent` but uses an in-process module-level cache (`_retrieval_cache` in `broken_agent/stateful_agent.py`). It is deployed with `--concurrency 1` and `--min-instances 2` so Cloud Run is forced to route concurrent requests to separate container instances, making the memory isolation failure visible.

```bash
gcloud builds submit \
  --config cloudbuild_broken.yaml \
  --project $GOOGLE_CLOUD_PROJECT \
  .

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
  --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=us-west1,RETRIEVAL_SERVICE_URL=$RETRIEVAL_SERVICE_URL
```

Copy the Service URL into `.env` as `BROKEN_AGENT_URL`.

Verify:
```bash
curl $BROKEN_AGENT_URL/health
# {"status": "healthy", "service": "policy-agent-broken"}
```

> **Why `--concurrency 1`?** Cloud Run defaults to 80 concurrent requests per instance. With a fast async client, all simultaneous requests complete before the autoscaler spins up a second instance. Setting concurrency to 1 ensures each in-flight request occupies exactly one instance, guaranteeing the load balancer must route concurrent requests to separate containers.

> **Why `--min-instances 2`?** Two always-warm instances means the load balancer always has two targets to choose from, making the split deterministic rather than probabilistic.

---

## Step 7 — Run the chapter demos

### Section 10.1 and 10.2 — Statelessness failure (broken agent)

```bash
uv run python broken_agent/run_stateless_failure.py
```

What to look for:

| Field | Section 10.1 | Section 10.2 |
|---|---|---|
| `container_id` | Same or different per run | Two different values |
| `cache_hits` | Integer (0 or higher) — never `"N/A"` | `0` on both workers |
| `unique_containers` | 1 or 2 | **2** |
| `shared_state` | True or False | **False** |

Section 10.2 should reliably show `unique_containers: 2` and `shared_state: False` on the first or second run.

### Section 10.3 — Fixed agent (stateless)

```bash
curl -X POST $AGENT_SERVICE_URL/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is the remote work policy?"}'
```

What to look for:
- `cache_hits` is `"N/A — stateless agent; no in-process cache exists"` (expected — this is correct behaviour)
- `context_count` is 5
- `retrieval_service_url` points to Service A

### Section 10.4 — Retrieval service directly

```bash
curl -X POST $RETRIEVAL_SERVICE_URL/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is the vacation policy?"}'
```

What to look for:
- `contexts` array with `text` and `relevance_score` fields
- `context_count` of 5

---

## Deployed service URLs (this chapter's GCP project)

| Service | URL |
|---|---|
| Service A: policy-retrieval | `https://policy-retrieval-946002739647.us-west1.run.app` |
| Service B (fixed): policy-agent | `https://policy-agent-klw32utc7a-uw.a.run.app` |
| Service B (broken): policy-agent-broken | `https://policy-agent-broken-946002739647.us-west1.run.app` |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `unique_containers: 1` every run | Service still at default concurrency=80 | Redeploy with `--concurrency 1 --min-instances 2` |
| `cache_hits: "N/A"` on broken agent | Script pointing at fixed agent URL | Set `BROKEN_AGENT_URL` in `.env`; check it takes precedence over `AGENT_SERVICE_URL` |
| `502` from policy-agent-broken | `RETRIEVAL_SERVICE_URL` not set on Cloud Run | Redeploy with `--set-env-vars` including `RETRIEVAL_SERVICE_URL` |
| `validate_services.py` fails | Service A or B not healthy | Run `curl <url>/health` on each service and check Cloud Run logs |
| Build fails: `COPY pyproject.toml` not found | Build context is wrong directory | Always run `gcloud builds submit` from repo root, not from a subdirectory |
| `SyntaxError` in run_stateless_failure.py | Curly-quote corruption from editor | Run `python3 -c "open('f').read().replace(...)"` to restore straight ASCII quotes |

---

## Build context note

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
