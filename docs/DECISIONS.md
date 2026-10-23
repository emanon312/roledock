# RoleDock Architecture Decisions

## ADR-001: Independent reconstruction
The code and synthetic content are newly created from a high-level public CV; never import source or documents from the employer.

## ADR-002: Role and tool gates are deterministic
The model may propose only known tools; membership in server-side `allowed_tools` is verified independently before dispatch. Each expert re-checks tool authorization. No model-produced role is trusted.

## ADR-003: Qdrant is only an index
Source text stays in a vetted authoritative chunk store. Qdrant carries only identifiers, ACL partition and content fingerprint. Pre-filter on authorized partitions, then verify IDs/partition/fingerprint against trusted source readback. On mismatch, deny rather than partially returning data.

## ADR-004: Initial RAG storage is intentionally constrained
Index reconstruction from the synthetic JSON is reliable for demo only. Index rebuild deletes the demo collection; production requires immutable source versions, durable source store and blue/green index aliases.

## ADR-005: Model compatibility without provider-specific tools
Only a common Chat Completions text request is assumed; the model is never supplied a direct shell, Git or database tool. Route output must be a JSON object with an allowed tool name. Invalid responses fail closed.

## ADR-006: LangGraph checkpoint is a development feature
SQLite checkpoint provides persistence for completed states, not a tested enterprise crash-recovery guarantee. State may contain raw retrieved text; secure and rotate stored files. Use `LANGGRAPH_STRICT_MSGPACK=true` and consider PostgreSQL for concurrency.

## ADR-007: Public demo is not a production auth system
Static keys are exposed in source; bind to localhost. All new endpoints inherit the same limitation. Do not upload proprietary materials or expose to the internet.
