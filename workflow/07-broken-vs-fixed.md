# 07. Broken architecture vs fixed architecture

## Caption

This comparison figure captures the chapter's central lesson. The broken design
keeps retrieval state inside the agent worker, while the fixed design places
retrieval behind a shared external FastAPI service backed by Vertex AI RAG
Engine.

## Mermaid

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

## What the reader should notice

- In the broken design, memory stays trapped inside one worker.
- In the fixed design, retrieval moves to a shared service boundary.
- Every worker can now reach the same retrieval system.
- The key change is architectural, not cosmetic.
