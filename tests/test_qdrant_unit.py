"""Adapter contract tests without Qdrant installed; integration test uses real Qdrant."""
import math
import sys
from types import ModuleType, SimpleNamespace
import pytest
from roledock.models import Document
from roledock.qdrant_adapter import QdrantVectorKnowledge, point_id_for
from roledock.security import AccessDenied


@pytest.fixture
def fake_qdrant(monkeypatch):
    # Fake only the thin SDK model constructors; driver logic is tested below.
    fake_pkg, models = ModuleType("qdrant_client"), ModuleType("qdrant_client.models")
    for name in ("Distance",):
        setattr(models, name, SimpleNamespace(COSINE="Cosine"))
    for name in ("PointStruct", "VectorParams", "FieldCondition", "MatchAny", "Filter"):
        setattr(models, name, lambda *args, **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_pkg)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", models)
    return models


class ToyEncoder:
    def encode(self, texts):
        return [self(x) for x in texts]

    def __call__(self, text):
        return [1., 0.] if "财务" in text else [0., 1.]


class FakeClient:
    def __init__(self):
        self.points = {}
        self.query_filter = None

    def collection_exists(self, name):
        return bool(self.points)

    def delete_collection(self, name):
        self.points = {}

    def create_collection(self, **kwargs):
        self.vector_params = kwargs["vectors_config"]

    def upload_points(self, **kwargs):
        self.points = {p.id: p for p in kwargs["points"]}

    def query_points(self, **kwargs):
        self.query_filter = kwargs["query_filter"]
        permitted = set(self.query_filter.must[0].match.any)
        out = []
        for p in self.points.values():
            if p.payload["partition"] not in permitted:
                continue
            dot = sum(a*b for a, b in zip(p.vector, kwargs["query"]))
            magnitude = (sum(a*a for a in p.vector) * sum(b*b for b in kwargs["query"]))**.5
            out.append(SimpleNamespace(id=p.id, score=dot/magnitude if magnitude else 0, payload=p.payload))
        out.sort(key=lambda p: -p.score)
        return SimpleNamespace(points=out[:kwargs["limit"]])


def build(fake_qdrant):
    docs = [Document("free", "research_public", "demo/free", "公开的研究资料"),
            Document("secret", "company_finance", "demo/secret", "私人财务审批信息")]
    client = FakeClient()
    vector = QdrantVectorKnowledge(client, ToyEncoder(), docs)
    vector.index_documents()
    return vector, client


def test_qdrant_index_filter_and_trusted_readback(fake_qdrant, service):
    vector, client = build(fake_qdrant)
    hits = vector.search("财务", service.profiles["investor"])
    assert {h.document_id for h in hits} == {"free"}
    assert client.query_filter.must[0].match.any == sorted(service.profiles["investor"].allowed_partitions)
    assert len(client.points) == 2
    assert all("text" not in p.payload for p in client.points.values())
    assert {h.document_id for h in vector.search("财务", service.profiles["finance"])} == {"secret"}


def test_qdrant_rejects_forged_partition(fake_qdrant, service):
    vector, client = build(fake_qdrant)
    p = next(point for point in client.points.values() if point.payload["source_id"] == "secret")
    p.payload["partition"] = "research_public"
    with pytest.raises(AccessDenied, match="partition|metadata"):
        vector.search("财务", service.profiles["investor"])


def test_qdrant_rejects_forged_fingerprint_and_identifier(fake_qdrant, service):
    vector, client = build(fake_qdrant)
    p = next(point for point in client.points.values() if point.payload["source_id"] == "free")
    p.payload["fingerprint"] = "malicious"
    with pytest.raises(AccessDenied, match="metadata"):
        vector.search("研究", service.profiles["investor"])


def test_qdrant_rejects_payload_body_even_if_injected(fake_qdrant, service):
    vector, client = build(fake_qdrant)
    p = next(point for point in client.points.values() if point.payload["source_id"] == "free")
    p.payload["text"] = "FORGED: Secret instructions"
    hits = vector.search("研究", service.profiles["investor"])
    assert all("FORGED" not in h.text for h in hits)


def test_qdrant_reindex_is_idempotent(fake_qdrant):
    vector, client = build(fake_qdrant)
    before = set(client.points)
    assert vector.index_documents() == 2
    assert set(client.points) == before
