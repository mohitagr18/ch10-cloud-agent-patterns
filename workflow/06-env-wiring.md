# 06. Environment-variable wiring at deploy time

## Caption

The two services are connected by deployment-time configuration. Resource
names, service URLs, and model choices come from environment variables rather
than from hardcoded values in the repository.

## Mermaid

```mermaid
flowchart LR
    A[.env file or gcloud deploy flags] --> B[Service A environment]
    A --> C[Service B environment]

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
- Service A discovers the RAG corpus through `RAG_CORPUS`.
- Deployment configuration is part of the architecture.
- This keeps the code portable across projects, regions, and environments.
