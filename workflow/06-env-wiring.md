# 06. Environment-variable wiring at deploy time

## Caption

The two services are connected at deployment time through environment variables.
No project IDs, URLs, corpus names, or model names are hardcoded in the code.

## Mermaid

```mermaid
flowchart LR
    A[.env or gcloud deploy flags] --> B[Service A env]
    A --> C[Service B env]

    B --> D[RAG_CORPUS]
    B --> E[GOOGLE_CLOUD_PROJECT]
    B --> F[GOOGLE_CLOUD_LOCATION]

    C --> G[RETRIEVAL_SERVICE_URL]
    C --> H[AGENT_MODEL]
    C --> I[GOOGLE_CLOUD_PROJECT]
    C --> J[GOOGLE_CLOUD_LOCATION]
```

## What the reader should notice

- Service B discovers Service A through `RETRIEVAL_SERVICE_URL`.
- Service A discovers the corpus through `RAG_CORPUS`.
- The deploy command is part of the architecture, not an afterthought.
- This wiring keeps the repository portable across projects and environments.
