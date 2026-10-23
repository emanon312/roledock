# Architecture (v0.3)

```text
X-Demo-Key → Principal derived server-side → Role Profile
          → LangGraph StateGraph (optional model route proposal)
             → policy gate → 3 specialist nodes
                ├─ retrieval: Qdrant filtered index → verified trusted Chunk → optional model synthesis
                ├─ research: bounded plan generation (no hidden tool execution)
                └─ document: approved PDF bytes registry (never untrusted paths)
             → result + optional SQLite checkpoint
          → metadata-only task audit (API)
```

## Trust boundaries
- `RoleProfile` is loaded from local controlled config. Client claims and model output cannot widen roles or tools.
- Qdrant payload is untrusted; only `TrustedChunks.readback` is permitted to return text. Checks include role partition, source ID, fingerprint and deterministic point UUID.
- Model sees only authorized retrieved text, not arbitrary document paths. Documents are explicitly described as untrusted evidence in synthesis prompts. Prompt isolation does not guarantee safety against all prompt injections.
- Repeated index rebuilds may cause downtime; do not run them during serving in real deployments.
- Shared Qdrant supports concurrent workers; local embedded Qdrant directory should NOT be opened by multiple processes concurrently.
- Checkpoint data is not the same as audit events. Checkpoint may contain question/snippets; audit only stores metadata.

## Staged functionality
**Offline**: deterministic lexical retrieval, role-aware router, local API without provider credentials.
**Integrated opt-in**: FastEmbed local BGE embeddings, Qdrant search, LangGraph expert graph, OpenAI-Compatible model, SQLite checkpoint example.
**Not provided**: enterprise SSO, actual provider availability, complete fault recovery, SiYuan syncing, production multi-tenant deployment.
