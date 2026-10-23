import pytest
from roledock.ingestion import chunk_document, manifest
from roledock.models import Document


def test_chunking_is_deterministic_and_overlapping():
    doc = Document('id', 'research_public', 'demo.md', 'abcdefghijklmnopqrst')
    chunks = chunk_document(doc, size=10, overlap=3)
    assert [c.text for c in chunks] == ['abcdefghij', 'hijklmnopq', 'opqrst']
    assert chunks[0].chunk_id == 'id:0000'
    assert chunks[0].fingerprint == chunk_document(doc, size=10, overlap=3)[0].fingerprint


def test_rejects_duplicate_document_ids():
    doc = Document('same', 'research_public', 'demo.md', 'text')
    with pytest.raises(ValueError, match='duplicate'):
        manifest([doc, doc])


def test_rejects_unsafe_window():
    doc = Document('id', 'p', 's', 'text')
    with pytest.raises(ValueError):
        chunk_document(doc, size=10, overlap=10)
