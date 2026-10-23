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


## ADR-008: Durable HITL uses out-of-band authorization, not model-produced approval
High-risk PDF read is paused with LangGraph `interrupt()` after role, tool and
approved-document checks. A reviewer must hold an independently authenticated
`compliance` or `admin` role, cannot be the requester, and writes a durable
approval/rejection record. `Command(resume=...)` is only a wake-up signal:
`approval_gate` re-reads the review ledger and revalidates file access. A
forged resume payload cannot authorize execution.

## ADR-009: Idempotent request intake, NOT exactly-once external side effects
A unique `(actor, request_key)` pair plus request fingerprint prevents
accidental duplicate scheduling. The runtime never automatically reruns an
incomplete non-approval node after a crash. A production integration would
require job leases, a transactional outbox, side-effect idempotency, retry
policies and observability. The v0.4 PDF tool is read-only.

## ADR-010: Reviewer gets only minimum approval context
Reviewer preview includes role, tool, and approved document ID, but no prompt
or document body. Reviews are immutable; a repeated identical submission is
idempotent only for the same reviewer. Persisted checkpoints can still carry
sensitive text, so local state and storage must remain private.
