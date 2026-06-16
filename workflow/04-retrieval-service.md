# 04. FastAPI as the retrieval boundary

## Caption

Service A wraps Vertex AI RAG Engine behind a small FastAPI interface. That
interface becomes the persistence boundary between agent reasoning and durable
retrieval.

## Mermaid

```mermaid
flowchart TD
    A[Service B: policy-agent] -->|POST /retrieve| B[Service A: policy-retrieval]
    B -->|Calls rag.retrieval_query()| C[Vertex AI RAG Engine]
    C -->|Retrieved contexts| B
    B -->|Returns JSON contexts| A
```

## What the reader should notice

- Service A is responsible only for retrieval.
- Service B is responsible only for agent orchestration.
- The services can scale and fail independently.
- The RAG corpus remains outside both running processes.
