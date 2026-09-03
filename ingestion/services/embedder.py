"""
Embedder service: abstraksi supaya provider embedding (bge-m3, provider
eksternal, dst.) bisa diganti tanpa mengubah command chunking/embedding.
"""
import threading

from django.conf import settings


class BaseEmbedder:
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class BgeM3Embedder(BaseEmbedder):
    """Menjalankan bge-m3 secara lokal lewat sentence-transformers."""

    model_name = "bge-m3"

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer("BAAI/bge-m3")

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()


class ExternalEmbedder(BaseEmbedder):
    """Untuk provider embedding eksternal lain via HTTP API (opsional)."""

    model_name = "external-provider"

    def __init__(self):
        import requests
        self._session = requests.Session()
        self._endpoint = settings.EXTERNAL_EMBEDDING_ENDPOINT
        self._api_key = settings.EXTERNAL_EMBEDDING_API_KEY

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._session.post(
            self._endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


_embedder_instance = None
_embedder_lock = threading.Lock()


def get_embedder() -> BaseEmbedder:
    provider = settings.EMBEDDING_PROVIDER
    global _embedder_instance

    if _embedder_instance is not None:
        return _embedder_instance

    with _embedder_lock:
        if _embedder_instance is not None:
            return _embedder_instance
        if provider == "bge-m3":
            _embedder_instance = BgeM3Embedder()
        elif provider == "external":
            _embedder_instance = ExternalEmbedder()
        else:
            raise ValueError(f"Provider embedding tidak dikenal: {provider}")

    return _embedder_instance
