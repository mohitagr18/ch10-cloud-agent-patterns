# 02. Concurrent workers do not share memory

## Caption

Concurrent traffic makes the state problem easier to see. Two requests can be
handled at the same time by separate workers, and each worker begins with its
own isolated in-process state.

## Mermaid

```mermaid
flowchart LR
    A[Concurrent request A] --> B[Worker 1 in container X]
    C[Concurrent request B] --> D[Worker 2 in container Y]
    B --> E[Local cache inside X]
    D --> F[Local cache inside Y]
    E -.no shared memory boundary.-> F
```

## What the reader should notice

- Concurrency increases the number of isolated worker memories.
- Cached retrievals and session state stay trapped inside one worker.
- A multi-worker backend is not a shared-memory system.
- This is why stateful agent servers become unreliable under real load.
