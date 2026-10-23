# Phase plan and acceptance tests

## Working now (offline)
- Seven server-side roles and twelve synthetic partitions; no user-driven role override
- Access-controlled lexical retrieval with no zero-match fallback
- Role/task routing, allowed tools, constrained PDF file ID registry
- SQLite metadata-only task audit with actor-scoped lookup
- Reproducible ingestion chunk manifest, SHA-256 fingerprints
- 18 original v0.1 **synthetic** matrix regressions plus additional unit tests

## Still outstanding (do not imply complete)
- Real Qdrant collection, vector ingestion and BGE/FastEmbed embeddings
- SiYuan authenticated synchronization and provenance-preserving source readback
- LangGraph SQLite/Postgres checkpoint end-to-end tested with resume/interrupt
- Real expert-agent use of an LLM with bounded planning and context limits
- Gateway process monitoring and meaningful multi-turn fault recovery
- Evaluation datasets and task metrics with documented denominators

## Safe next increment
1. Wire a trusted chunk repository into Qdrant semantic retrieval; seed synthetic data.
2. Replace the duplicated prototype LangGraph route with one policy-gated graph.
3. Add SQLite-backed checkpoint tests and recovery demo.
