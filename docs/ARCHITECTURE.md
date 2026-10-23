# Architecture (v0.4)

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


## v0.4 local durable runtime

```text
POST /v1/runtime/tasks [authenticated role, request_key]
    → ledger: UNIQUE(actor, request_key) + request fingerprint
    → LangGraph: load_role → route + permission gate
          ├─ knowledge / research → finish
          └─ PDF → approved file ID check
                       ↓
                approval_gate: interrupt()
                       ↓
GET /v1/runtime/reviews/{id} [compliance/admin, no self-review]
POST /v1/runtime/tasks/{id}/review {approved: bool}
                       ↓
                task ledger stores reviewer decision (trusted)
                       ↓
                Command(resume=...) → ledger check → PDF read again → finish
```

`TaskLedger` records task IDs, actors, role, request-hash, file ID, status and
reviewer decision, **not** raw questions, answers or parsed PDF. `SqliteSaver`
holds the full graph state and can store the question and parsed content: use
restricted local storage and explicit retention. Separate task IDs are stable
across retries of the same idempotency key. No arbitrary filesystem paths or
shell are permitted.

**Recovery guarantee boundary**: the demo recovers pending human approvals
across process restarts. If a non-approval step crashes partway through, it is
marked failed rather than auto-replayed. For any future side-effecting tool,
add a transactional outbox/tool-specific idempotency key and reconciliation;
LangGraph checkpointing alone is not exactly-once execution. SQLite and
`RLock` protect a *single local worker*, not a distributed deployment.

The previous `/v1/tasks` and `/v1/agent/tasks` routes remain unchanged,
so approval enforcement must be selected through the new runtime endpoints.
The demo has publicly known static API keys; never bind it to a public address.
