"""Text -> unit-normalized float32 vectors.

    hash    offline bag-of-words hashing. Zero setup; fine for tests, weak for semantics.
    ollama  any Ollama embedding model (default: embeddinggemma-2:570m). `ollama pull embeddinggemma-2:570m`.
"""

import hashlib
import re
import time
from typing import Protocol

import numpy as np
import requests

from shared.settings import Settings


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray: ...


def _normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).astype(np.float32)


class HashEmbedder:
    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.name = f"hash-{dim}"

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for tok in re.findall(r"[a-z0-9_]+", text.lower()):
                h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "little")
                out[i, h % self.dim] += 1.0
        return _normalize(out)


class OllamaEmbedder:
    def __init__(
        self, url: str, model: str, timeout: float = 120.0, batch_size: int = 32, keep_alive: str | None = None
    ):
        self.url, self.model, self.timeout, self.batch_size = url, model, timeout, batch_size
        self.keep_alive = keep_alive
        self.name = f"ollama-{model}"

    def warm_up(self, attempts: int = 3) -> None:
        """Load the embedding model now; Ollama may 500 while it is still loading, so retry."""
        for i in range(attempts):
            try:
                self.embed(["warm-up"], is_query=True)
                return
            except requests.RequestException:
                if i == attempts - 1:
                    raise
                time.sleep(2 * (i + 1))

    def _prefix(self, text: str, is_query: bool) -> str:
        # EmbeddingGemma (v1 and v2, same prefixes) is trained with task prompts; other models get raw text.
        if "embeddinggemma" not in self.model:
            return text
        return f"task: search result | query: {text}" if is_query else f"title: none | text: {text}"

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vecs: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [self._prefix(t, is_query) for t in texts[i : i + self.batch_size]]
            body = {"model": self.model, "input": batch}
            if self.keep_alive:
                body["keep_alive"] = self.keep_alive
            r = requests.post(f"{self.url}/api/embed", json=body, timeout=self.timeout)
            # Ollama 500s while (re)loading or after its runner crashes, and 400s when a model
            # cannot be scheduled right now (another model is filling the VRAM, a pull is running).
            # Both clear on their own, so back off once rather than failing the request.
            if r.status_code >= 400:
                time.sleep(2)
                r = requests.post(f"{self.url}/api/embed", json=body, timeout=self.timeout)
            r.raise_for_status()
            vecs.extend(r.json()["embeddings"])
        return _normalize(np.asarray(vecs, dtype=np.float32))


def get_embedder(settings: Settings) -> Embedder:
    if settings.embed_provider == "ollama":
        return OllamaEmbedder(
            settings.ollama_url, settings.embed_model, settings.request_timeout_s,
            keep_alive=settings.ollama_keep_alive,
        )
    return HashEmbedder()
