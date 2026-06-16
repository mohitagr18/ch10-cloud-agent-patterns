# 07. Broken architecture vs fixed architecture

## Caption

This side-by-side comparison shows the chapter's main lesson in one figure. The
broken version keeps retrieval state inside the agent worker. The fixed version
moves retrieval behind an external FastAPI service backed by Vertex AI RAG
Engine.

## Mermaid

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

## What the reader should notice

- In the broken design, memory is trapped inside whichever worker handled the last request.
- In the fixed design, retrieval leaves the worker and moves to a shared external service.
- The fixed version is reliable because every worker can reach the same retrieval boundary.
- The architecture changes, not just the code style.
