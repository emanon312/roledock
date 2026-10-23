"""Qdrant retrieval with trusted-source readback (never trust payload text)."""
from collections.abc import Callable
from .models import Document, Hit, RoleProfile
from .security import AccessDenied, require_partition


class QdrantSecureRetriever:
    """Qdrant returns identifiers and scores; a trusted document store returns content.

    readback(document_id, profile) MUST check the document's authoritative ACL.
    The adapter fails closed if the stored partition and payload metadata differ.
    """

    def __init__(self, client, collection: str, embed: Callable[[str], list[float]],
                 readback: Callable[[str, RoleProfile], Document]):
        self.client = client
        self.collection = collection
        self.embed = embed
        self.readback = readback

    def search(self, query: str, profile: RoleProfile, limit: int = 5) -> list[Hit]:
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        if not profile.allowed_partitions:
            return []
        acl_filter = Filter(must=[FieldCondition(
            key="partition", match=MatchAny(any=sorted(profile.allowed_partitions))
        )])
        response = self.client.query_points(
            collection_name=self.collection,
            query=self.embed(query),
            query_filter=acl_filter,
            with_payload=True,
            limit=min(max(1, limit), 10),
        )
        hits: list[Hit] = []
        for point in response.points:
            payload = point.payload or {}
            part = payload.get("partition")
            doc_id = payload.get("document_id")
            if not isinstance(part, str) or not isinstance(doc_id, str):
                raise AccessDenied("invalid_retrieval_metadata")
            require_partition(profile, part)
            # Trusted readback authenticates both access and document existence.
            doc = self.readback(doc_id, profile)
            if doc.id != doc_id or doc.partition != part:
                raise AccessDenied("source_metadata_mismatch")
            require_partition(profile, doc.partition)
            hits.append(Hit(doc.id, doc.partition, doc.source, doc.text, float(point.score)))
        return hits
