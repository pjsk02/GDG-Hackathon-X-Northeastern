"""Text -> unit-normalized float32 vectors.

    hash    offline bag-of-words hashing. Zero setup; fine for tests, weak for semantics.
    ollama  any Ollama embedding model (default: embeddinggemma-2:570m). `ollama pull embeddinggemma-2:570m`.
    gemini  Google AI Studio embeddings (GEMINI_EMBED_MODEL, default gemini-embedding-001). Needs GEMINI_API_KEY.

Contract (owner: Rithwik, role C): `get_embedder(settings) -> Embedder`; every embedder has `name` (vectors are
tagged with it in the store) and `embed(texts, *, is_query=False) -> np.ndarray` of unit-normalized float32 rows.
"""

import hashlib
import importlib
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


class GeminiEmbedder:
    """Gemini embeddings via the google-genai SDK, with retrieval task types and retry on 429/5xx."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-embedding-001",
        batch_size: int = 64,
        timeout: float = 30.0,
        max_retries: int = 6,
        backoff_s: float = 2.0,
        max_backoff_s: float = 60.0,
        output_dim: int | None = 768,
    ):
        if not api_key:
            raise ValueError("EMBED_PROVIDER=gemini needs GEMINI_API_KEY in .env")
        self.api_key, self.model, self.batch_size, self.timeout = api_key, model, batch_size, timeout
        # gemini-embedding-001 returns 3072 dims by default; it is trained so a 768 prefix keeps nearly all the
        # quality at a quarter of the index size and search time. None = model default.
        self.output_dim = output_dim
        self.max_retries, self.backoff_s, self.max_backoff_s = max_retries, backoff_s, max_backoff_s
        self.name = f"gemini-{model}"
        self._client = None  # created on first use; tests inject a fake
        self._sleep = time.sleep

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as e:
                raise RuntimeError('google-genai not installed: pip install -e ".[gemini]"') from e
            self._client = genai.Client(
                api_key=self.api_key, http_options=types.HttpOptions(timeout=int(self.timeout * 1000))  # milliseconds
            )
        return self._client

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        code = getattr(exc, "code", None)  # google.genai.errors.APIError carries the HTTP status here
        if isinstance(code, int):
            return code == 429 or code >= 500
        # Network trouble (timeouts, dropped connections) never reaches the API, so it has no status code.
        # google-genai 3.x ships on httpx2; older versions use httpx. Accept either.
        for mod in ("httpx2", "httpx"):
            try:
                transport_error = importlib.import_module(mod).TransportError
            except (ImportError, AttributeError):
                continue
            if isinstance(exc, transport_error):
                return True
        return False

    def _embed_batch(self, batch: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        client = self._get_client()
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.output_dim)
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.models.embed_content(model=self.model, contents=batch, config=config)
                if len(resp.embeddings) != len(batch):
                    raise RuntimeError(f"Gemini returned {len(resp.embeddings)} embeddings for {len(batch)} texts")
                return [e.values for e in resp.embeddings]
            except Exception as e:
                if attempt == self.max_retries or not self._retryable(e):
                    raise
                self._sleep(min(self.max_backoff_s, self.backoff_s * 2**attempt))
        raise AssertionError("unreachable")

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
        vecs: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vecs.extend(self._embed_batch(texts[i : i + self.batch_size], task_type))
        return _normalize(np.asarray(vecs, dtype=np.float32))


def get_embedder(settings: Settings) -> Embedder:
    if settings.embed_provider == "gemini":
        return GeminiEmbedder(
            settings.gemini_api_key, settings.gemini_embed_model, settings.gemini_embed_batch,
            settings.gemini_timeout_s,
        )
    if settings.embed_provider == "ollama":
        return OllamaEmbedder(
            settings.ollama_url, settings.embed_model, settings.request_timeout_s,
            keep_alive=settings.ollama_keep_alive,
        )
    return HashEmbedder()
