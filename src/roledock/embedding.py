"""FastEmbed-based local embedding; loading is lazy and the model may download on first use."""
from collections.abc import Sequence

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


class FastEmbedEncoder:
    def __init__(self, model_name: str = DEFAULT_MODEL, model=None):
        self.model_name = model_name
        self._model = model

    @property
    def model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError("Install RAG extras: pip install -e '.[rag]'") from exc
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [list(map(float, vec)) for vec in self.model.embed(list(texts))]
        if len(vectors) != len(texts) or not vectors or not vectors[0]:
            raise ValueError("embedding_count_or_dimension_mismatch")
        dimension = len(vectors[0])
        if any(len(v) != dimension for v in vectors):
            raise ValueError("embedding_dimension_mismatch")
        return vectors

    def __call__(self, text: str) -> list[float]:
        return self.encode([text])[0]
