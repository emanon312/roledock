from roledock.embedding import FastEmbedEncoder
import pytest


class FakeEmbedding:
    def embed(self, texts):
        for text in texts:
            yield [float(len(text)), 1.0]


def test_fastembed_adapter_contract_without_model_download():
    encoder = FastEmbedEncoder(model=FakeEmbedding())
    assert encoder("中文") == [2.0, 1.0]
    assert encoder.encode(["一", "两字"]) == [[1.0, 1.0], [2.0, 1.0]]
    assert encoder.encode([]) == []


class BadEmbedding:
    def embed(self, texts):
        yield [1.0]


def test_embedding_count_is_checked():
    encoder = FastEmbedEncoder(model=BadEmbedding())
    with pytest.raises(ValueError, match="count"):
        encoder.encode(["a", "b"])
