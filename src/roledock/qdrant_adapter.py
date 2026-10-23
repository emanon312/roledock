"""Qdrant vector retrieval with authoritative chunk readback and ACL defense-in-depth.

The vector DB is an untrusted index. No textual body from payload is returned to users
or models; all snippets are taken from the verified, trusted chunk collection.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from .ingestion import Chunk, chunk_document, manifest
from .models import Document, Hit, RoleProfile
from .security import AccessDenied, require_partition


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...
    def __call__(self, text: str) -> list[float]: ...


class TrustedChunks:
    """Authoritative in-process source for vetted documents, NOT a persisted document DB.

    Restarting reconstructs chunks from the same approved source material. If source
    materials change, reindex the collection before allowing retrieval.
    """

    def __init__(self, documents: list[Document], size: int = 450, overlap: int = 70):
        items = manifest(documents) if (size, overlap) == (450, 70) else [
            chunk for doc in documents for chunk in chunk_document(doc, size, overlap)
        ]
        self._chunks = {item.chunk_id: item for item in items}
        if len(self._chunks) != len(items):
            raise ValueError("duplicate_chunk_id")

    def list_chunks(self) -> list[Chunk]:
        return list(self._chunks.values())

    def readback(self, chunk_id: str, profile: RoleProfile) -> Chunk:
        chunk = self._chunks.get(chunk_id)
        if chunk is None:
            raise AccessDenied("chunk_missing_in_authoritative_store")
        require_partition(profile, chunk.partition)
        return chunk


def point_id_for(chunk: Chunk) -> str:
    return str(uuid5(NAMESPACE_URL, f"roledock:chunk:{chunk.chunk_id}"))


@dataclass(frozen=True)
class QdrantSettings:
    collection: str = "roledock_chunks_v1"
    score_threshold: float | None = None


class QdrantSecureRetriever:
    def __init__(self, client, collection: str, embed: Callable[[str], list[float]],
                 readback: Callable[[str, RoleProfile], Chunk], score_threshold: float | None = None):
        self.client = client
        self.collection = collection
        self.embed = embed
        self.readback = readback
        self.score_threshold = score_threshold

    def search(self, query: str, profile: RoleProfile, limit: int = 5) -> list[Hit]:
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        if not profile.allowed_partitions or limit <= 0:
            return []
        acl_filter = Filter(must=[FieldCondition(
            key="partition", match=MatchAny(any=sorted(profile.allowed_partitions))
        )])
        result = self.client.query_points(
            collection_name=self.collection,
            query=self.embed(query),
            query_filter=acl_filter,
            with_payload=True,
            limit=min(limit, 10),
            score_threshold=self.score_threshold,
        )
        hits: list[Hit] = []
        seen: set[str] = set()
        for point in result.points:
            payload = point.payload or {}
            part, chunk_id = payload.get("partition"), payload.get("chunk_id")
            source_id, fingerprint = payload.get("source_id"), payload.get("fingerprint")
            if not all(isinstance(x, str) and x for x in (part, chunk_id, source_id, fingerprint)):
                raise AccessDenied("invalid_retrieval_metadata")
            require_partition(profile, part)
            chunk = self.readback(chunk_id, profile)
            if (chunk.partition != part or chunk.source_id != source_id
                    or chunk.fingerprint != fingerprint or point.id != point_id_for(chunk)):
                raise AccessDenied("source_metadata_mismatch")
            require_partition(profile, chunk.partition)
            if chunk_id not in seen:
                seen.add(chunk_id)
                hits.append(Hit(chunk.source_id, chunk.partition, chunk.source, chunk.text, float(point.score)))
        return hits


class QdrantVectorKnowledge:
    """Real Qdrant collection with separate trusted in-memory content store.

    index_documents must be run after data changes and BEFORE serving queries.
    The index holds identifiers/partitions/fingerprints, never source text.
    """

    def __init__(self, client, encoder: Encoder, documents: list[Document],
                 settings: QdrantSettings = QdrantSettings()):
        self.client, self.encoder, self.settings = client, encoder, settings
        self.trusted = TrustedChunks(documents)
        self.retriever = QdrantSecureRetriever(
            client, settings.collection, encoder, self.trusted.readback, settings.score_threshold
        )

    def index_documents(self) -> int:
        from qdrant_client.models import Distance, PointStruct, VectorParams
        chunks = self.trusted.list_chunks()
        if not chunks:
            raise ValueError("no_documents_to_index")
        vectors = self.encoder.encode([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("embedding_count_mismatch")
        dim = len(vectors[0])
        if dim <= 0 or any(len(v) != dim for v in vectors):
            raise ValueError("embedding_dimension_mismatch")
        # Explicit recreation removes stale points from prior document versions.
        # During production migration use versioned collections + alias swap instead.
        if self.client.collection_exists(self.settings.collection):
            self.client.delete_collection(self.settings.collection)
        self.client.create_collection(
            collection_name=self.settings.collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        points = [PointStruct(
            id=point_id_for(chunk), vector=vec,
            payload={"partition": chunk.partition, "source_id": chunk.source_id,
                     "chunk_id": chunk.chunk_id, "fingerprint": chunk.fingerprint}
        ) for chunk, vec in zip(chunks, vectors, strict=True)]
        self.client.upload_points(collection_name=self.settings.collection, points=points, wait=True)
        return len(points)

    def search(self, query: str, profile: RoleProfile, limit: int = 5) -> list[Hit]:
        return self.retriever.search(query, profile, limit=limit)
