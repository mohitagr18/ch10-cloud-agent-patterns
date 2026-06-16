# Chapter 10 workflow diagrams

This appendix-style file gathers every Mermaid diagram for Chapter 10 in one
place, in chapter order. Use it for editorial review, figure planning, or
manuscript handoff.

---

## 10.1 Local success, cloud failure

```mermaid
flowchart TD
    A[Request 1 from reader] --> B[Cloud Run container A]
    B --> C[Retrieval result cached in process memory]
    D[Request 2 from reader] --> E[Cloud Run container B]
    E --> F[Process memory starts empty]

    C -.memory is not shared across containers.-> F
```

**Figure intent:** Show that local success can hide the loss of in-process state
once requests begin landing on separate cloud containers.

---

## 10.2 Concurrent workers do not share memory

```mermaid
flowchart LR
    A[Concurrent request A] --> B[Worker 1 in container X]
    C[Concurrent request B] --> D[Worker 2 in container Y]
    B --> E[Local cache inside X]
    D --> F[Local cache inside Y]
    E -.no shared memory boundary.-> F
```

**Figure intent:** Show that concurrent requests multiply isolated worker
memories rather than creating a shared stateful system.

---

## 10.3 The stateless fix

```mermaid
flowchart TD
    A[Reader request] --> B[Stateless agent worker]
    B --> C[HTTP request to retrieval service]
    C --> D[Vertex AI RAG corpus]
    D --> C
    C --> B
    B --> E[Grounded response returned to reader]
```

**Figure intent:** Show that the fix is architectural. Retrieval becomes an
external shared capability instead of a local worker detail.

---

## 10.4 FastAPI as the retrieval boundary

```mermaid
flowchart TD
    A[Service B: policy-agent] -->|POST /retrieve| B[Service A: policy-retrieval]
    B -->|rag.retrieval_query()| C[Vertex AI RAG Engine]
    C --> B
    B -->|JSON contexts| A
```

**Figure intent:** Show the retrieval boundary introduced by the chapter.

---

## 10.5 End-to-end resilient cloud flow

```mermaid
flowchart TD
    A[Reader or test client] -->|POST /query| B[Cloud Run Service B
policy-agent]
    B -->|POST /retrieve| C[Cloud Run Service A
policy-retrieval]
    C -->|RAG query| D[Vertex AI RAG Engine]
    D --> C
    C -->|Retrieved contexts| B
    B -->|Grounded answer| A
```

**Figure intent:** Show the complete production path from user request to
retrieved context to grounded answer.

---

## Deployment wiring

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

**Figure intent:** Show that service discovery and cloud configuration are set
at deployment time rather than embedded in source code.

---

## Broken vs fixed comparison

```mermaid
flowchart LR
    subgraph Broken[Broken cloud architecture]
        A1[Reader request] --> B1[Cloud Run agent worker A]
        B1 --> C1[In-process cache]
        D1[Next request] --> E1[Cloud Run agent worker B]
        E1 --> F1[Empty in-process cache]
        C1 -.cached state does not cross worker boundaries.-> F1
    end

    subgraph Fixed[Fixed cloud architecture]
        A2[Reader request] --> B2[Stateless Cloud Run agent]
        B2 --> C2[FastAPI retrieval service]
        C2 --> D2[Vertex AI RAG Engine]
        D2 --> C2
        C2 --> B2
        B2 --> E2[Grounded response]
    end
```

**Figure intent:** Provide one summary figure for the chapter's central
architectural contrast.
