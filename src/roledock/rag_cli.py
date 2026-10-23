"""Explicit, trusted ingestion entrypoint. Never callable as an agent tool."""
import argparse
import os
from pathlib import Path

from .embedding import FastEmbedEncoder
from .knowledge import InMemoryKnowledge
from .qdrant_adapter import QdrantSettings, QdrantVectorKnowledge
from .runtime import ROOT


def build_vector_knowledge() -> QdrantVectorKnowledge:
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError("Install RAG extras: pip install -e '.[rag]'") from exc
    url = os.getenv("ROLEDOCK_QDRANT_URL", "").strip()
    client = QdrantClient(url=url) if url else QdrantClient(path=os.getenv("ROLEDOCK_QDRANT_PATH", ".qdrant"))
    documents = InMemoryKnowledge.from_json(ROOT / "demo_data" / "documents.json").all_documents_for_admin_seed()
    return QdrantVectorKnowledge(client, FastEmbedEncoder(), documents,
                                 settings=QdrantSettings(os.getenv("ROLEDOCK_QDRANT_COLLECTION", "roledock_chunks_v1")))


def main():
    parser = argparse.ArgumentParser(description="Ingest synthetic, approved RoleDock documents")
    parser.add_argument("command", choices=["index"])
    options = parser.parse_args()
    if options.command == "index":
        count = build_vector_knowledge().index_documents()
        print(f"Indexed {count} authoritative chunks (synthetic demo data only)")


if __name__ == "__main__":
    main()
