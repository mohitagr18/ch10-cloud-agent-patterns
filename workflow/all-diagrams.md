# Chapter 10 workflow diagrams

This appendix-style file collects every Mermaid diagram for Chapter 10 in one
place, in chapter order. Use it as an editorial handoff document, a review aid,
or a quick source for manuscript figures.

---

## 10.1 Local success, cloud failure

```mermaid
flowchart TD
    A[Reader sends Request 1] --> B[Cloud Run container A]
    B --> C[In-process cache stores retrieval result]
    D[Reader sends Request 2] --> E[Cloud Run container B]
    E --> F[Container B has empty in-process cache]

    C -.not shared.-> F
```

**Figure intent:** Show that the second cloud request may land on a different
container, so in-process state disappears.

---

## 10.2 Concurrent workers do not share memory

```mermaid
flowchart LR
    A[Concurrent Request A] --> B[Worker 1 / Container X]
    C[Concurrent Request B] --> D[Worker 2 / Container Y]
    B --> E[Local cache in X]
    D --> F[Local cache in Y]
    E -.not shared.-> F
```

**Figure intent:** Show that concurrency creates multiple isolated memory
islands, not a shared stateful backend.

---

## 10.3 The stateless fix

```mermaid
flowchart TD
    A[Reader request] --> B[Stateless agent worker]
    B --> C[HTTP call to retrieval service]
    C --> D[Vertex AI RAG corpus]
    D --> C
    C --> B
    B --> E[Grounded response]
```

**Figure intent:** Show that the fix is architectural. Retrieval moves out of
process and becomes externally shared.

---

## 10.4 FastAPI as the retrieval boundary

```mermaid
flowchart TD
    A[Service B: policy-agent] -->|POST /retrieve| B[Service A: policy-retrieval]
    B -->|rag.retrieval_query()| C[Vertex AI RAG Engine]
    C --> B
    B -->|JSON contexts| A
```

**Figure intent:** Show the new service boundary introduced by the chapter.

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
    C -->|retrieved contexts| B
    B -->|grounded answer| A
```

**Figure intent:** Show the full production path from client request to grounded
answer.

---

## Deployment wiring

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

**Figure intent:** Show that service discovery and cloud configuration happen at
deploy time, not through hardcoded values.

---

## Broken vs fixed comparison

```mermaid
flowchart LR
    subgraph Broken[Broken cloud architecture]
        A1[Reader request] --> B1[Cloud Run agent worker A]
        B1 --> C1[In-process cache]
        D1[Next request] --> E1[Cloud Run agent worker B]
        E1 --> F1[Empty in-process cache]
        C1 -.not shared.-> F1
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

**Figure intent:** Provide one summary visual for the chapter's core argument.
