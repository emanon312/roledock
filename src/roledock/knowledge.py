"""ACL-first retrieval and defense-in-depth readback."""
import json
import re
from pathlib import Path
from .models import Document, Hit, RoleProfile
from .security import AccessDenied, require_partition


def _terms(text: str) -> set[str]:
    # Demo only: lexical tokens and CJK bigrams; replace with BGE/FastEmbed later.
    lowered = text.casefold()
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
    words.update(cjk[i] + cjk[i+1] for i in range(len(cjk)-1))
    return words


class InMemoryKnowledge:
    """Deterministic offline demo; NOT a semantic vector database."""

    def __init__(self, documents: list[Document]):
        self._docs = {d.id: d for d in documents}

    @classmethod
    def from_json(cls, path: str | Path) -> "InMemoryKnowledge":
        docs = [Document(**item) for item in json.loads(Path(path).read_text(encoding="utf-8"))]
        return cls(docs)

    def search(self, query: str, profile: RoleProfile, limit: int = 5) -> list[Hit]:
        if not profile.allowed_partitions:
            return []
        terms = _terms(query)
        matches = []
        for doc in self._docs.values():
            # Permission filter BEFORE ranking: forbidden docs never enter candidates.
            if doc.partition not in profile.allowed_partitions:
                continue
            overlap = len(terms.intersection(_terms(doc.text)))
            # Refuse irrelevant fallback results; avoid unrelated information leakage.
            if overlap > 0:
                matches.append((overlap, doc))
        matches.sort(key=lambda item: (-item[0], item[1].id))
        hits = []
        for score, doc in matches[:max(0, min(limit, 10))]:
            # Second independent check before returning potentially sensitive bytes.
            require_partition(profile, doc.partition)
            hits.append(Hit(doc.id, doc.partition, doc.source, doc.text, float(score)))
        return hits

    def readback(self, document_id: str, profile: RoleProfile) -> Document:
        doc = self._docs.get(document_id)
        if doc is None:
            raise KeyError("document_not_found")
        require_partition(profile, doc.partition)
        return doc

    def all_documents_for_admin_seed(self) -> list[Document]:
        return list(self._docs.values())
