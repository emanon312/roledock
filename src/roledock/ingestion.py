"""Offline ingestion to reproducible, source-addressable chunks.

No filesystem paths are accepted from an agent. Caller supplies a vetted source ID
and text already loaded through an authorized ingestion boundary.
"""
from dataclasses import dataclass
from hashlib import sha256
from .models import Document


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_id: str
    partition: str
    source: str
    text: str
    ordinal: int
    fingerprint: str


def chunk_document(document: Document, size: int = 450, overlap: int = 70) -> list[Chunk]:
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("invalid_chunk_window")
    if not document.id or not document.partition or not document.source:
        raise ValueError("missing_document_metadata")
    text = document.text.strip()
    if not text:
        return []
    window = []
    position = 0
    while position < len(text):
        fragment = text[position:position + size]
        fingerprint = sha256(fragment.encode("utf-8")).hexdigest()
        window.append(Chunk(
            chunk_id=f"{document.id}:{len(window):04d}",
            source_id=document.id,
            partition=document.partition,
            source=document.source,
            text=fragment,
            ordinal=len(window),
            fingerprint=fingerprint,
        ))
        if position + size >= len(text):
            break
        position += size - overlap
    return window


def manifest(documents: list[Document]) -> list[Chunk]:
    seen = set()
    chunks = []
    for doc in documents:
        if doc.id in seen:
            raise ValueError("duplicate_document_id")
        seen.add(doc.id)
        chunks.extend(chunk_document(doc))
    return chunks
