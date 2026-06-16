# 04. FastAPI as the retrieval boundary

## Caption

Service A wraps Vertex AI RAG Engine behind a small HTTP API. That service
becomes the persistence boundary that every agent worker can call.

## Mermaid

```mermaid
flowchart TD
    A[Service B: policy-agent] -->|POST /retrieve| B[Service A: policy-retrieval]
    B -->|rag.retrieval_query()| C[Vertex AI RAG Engine]
    C --> B
    B -->|JSON contexts| A
```

## What the reader should notice

- Service A has one job: retrieval.
- Service B has one job: agent orchestration.
- The two services scale independently.
- The RAG corpus lives outside both processes.
