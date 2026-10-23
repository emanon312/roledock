# Architecture decision records — RoleDock (reconstruction)

## ADR-001: Rebuild, do not mimic unknown historical implementation

The original internship used a mixed agent stack, but internals are not documented
well enough to reproduce exactly. We deliberately rebuild with one LangGraph
orchestration boundary and a deterministic authorization layer. Do not claim
this was the employer's actual implementation.

## ADR-002: Role first, task second

The authenticated principal maps to a server-side role profile; only then can a
router propose a specialist/tool. Tool execution validates authority again.
User messages and retrieved documents can never alter the active role.

## ADR-003: Investment-oriented roles

Initial roles: research/investor, deal execution, IR, finance, operations,
compliance, plus a demo-only admin profile. The role/partition matrix is a
reconstruction based on business requirements, not a recovered employer policy.
Demo admin has broad read permissions for testing; it must not be copied into
production access control.

## ADR-004: Trusted source vs vector index

A vector index is not an authority for original document bytes. It provides
candidate document IDs, scores and partition tags. All content must be read from
an authoritative source with a separate ACL check, and the source partition must
match the indexed payload. There is no permissive fallback.

## ADR-005: Privacy-preserving audit

Only actor, role, selected expert/tool, task ID and status are stored in the
offline audit journal. Prompts and retrieved text are excluded. SQLite demo
journal is separate from future LangGraph checkpoint storage.

## ADR-006: Source honesty

All synthetic documents, fabricated role matrix, and newly created evaluation
cases must be clearly labeled. Numbers from the original resume are not to be
represented as independently reproduced measures.
