"""GeminiEmbedder, checked offline with a fake client (no API key or network)."""

import importlib.util
from types import SimpleNamespace

import numpy as np
import pytest
from google.genai import errors

from memory.embedder import GeminiEmbedder, HashEmbedder, get_embedder
from shared.settings import Settings

# google-genai 3.x uses httpx2; older versions use httpx.
httpx = pytest.importorskip("httpx2") if importlib.util.find_spec("httpx2") else pytest.importorskip("httpx")


class FakeModels:
    """Stands in for client.models: records calls and fails the first `failures` of them."""

    def __init__(self, failures: list[Exception] | None = None, dim: int = 4):
        self.calls: list[dict] = []
        self.failures = list(failures or [])
        self.dim = dim

    def embed_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "task_type": config.task_type,
                           "dim": config.output_dimensionality})
        if self.failures:
            raise self.failures.pop(0)
        # Deterministic, non-unit vectors so normalization is visible.
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[float(len(t) + j) for j in range(self.dim)]) for t in contents]
        )


def _embedder(models: FakeModels, **kw) -> tuple[GeminiEmbedder, list[float]]:
    emb = GeminiEmbedder("test-key", model="gemini-embedding-001", **kw)
    emb._client = SimpleNamespace(models=models)
    slept: list[float] = []
    emb._sleep = slept.append
    return emb, slept


def _api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


def test_name_and_unit_float32_rows():
    emb, _ = _embedder(FakeModels())
    assert emb.name == "gemini-gemini-embedding-001"
    out = emb.embed(["a", "bb", "ccc"])
    assert out.shape == (3, 4) and out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)


def test_task_type_follows_is_query():
    models = FakeModels()
    emb, _ = _embedder(models)
    emb.embed(["doc"])
    emb.embed(["question"], is_query=True)
    assert [c["task_type"] for c in models.calls] == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


def test_requests_768_dims_by_default():
    models = FakeModels()
    emb, _ = _embedder(models)
    emb.embed(["doc"])
    assert models.calls[0]["dim"] == 768
    models2 = FakeModels()
    emb2, _ = _embedder(models2, output_dim=None)
    emb2.embed(["doc"])
    assert models2.calls[0]["dim"] is None


def test_batches_keep_order():
    models = FakeModels()
    emb, _ = _embedder(models, batch_size=2)
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    out = emb.embed(texts)
    assert [len(c["contents"]) for c in models.calls] == [2, 2, 1]
    assert [t for c in models.calls for t in c["contents"]] == texts
    assert np.allclose(out, emb.embed(["a"]).tolist() + emb.embed(["bb", "ccc", "dddd", "eeeee"]).tolist())


def test_empty_input_makes_no_call():
    models = FakeModels()
    emb, _ = _embedder(models)
    assert emb.embed([]).shape == (0, 0)
    assert models.calls == []


@pytest.mark.parametrize("exc", [_api_error(429), _api_error(503), httpx.ConnectError("down")])
def test_retries_rate_limits_server_and_network_errors(exc):
    models = FakeModels(failures=[exc, exc])
    emb, slept = _embedder(models, backoff_s=1.0)
    assert emb.embed(["a"]).shape == (1, 4)
    assert len(models.calls) == 3
    assert slept == [1.0, 2.0]  # exponential backoff


def test_backoff_is_capped():
    models = FakeModels(failures=[_api_error(429)] * 5)
    emb, slept = _embedder(models, backoff_s=10.0, max_backoff_s=25.0)
    emb.embed(["a"])
    assert slept == [10.0, 20.0, 25.0, 25.0, 25.0]


def test_client_errors_are_not_retried():
    models = FakeModels(failures=[_api_error(400)])
    emb, slept = _embedder(models)
    with pytest.raises(errors.APIError):
        emb.embed(["a"])
    assert len(models.calls) == 1 and slept == []


def test_gives_up_after_max_retries():
    models = FakeModels(failures=[_api_error(500)] * 10)
    emb, slept = _embedder(models, max_retries=2)
    with pytest.raises(errors.APIError):
        emb.embed(["a"])
    assert len(models.calls) == 3 and len(slept) == 2


def test_wrong_embedding_count_is_an_error():
    class ShortModels(FakeModels):
        def embed_content(self, model, contents, config):
            resp = super().embed_content(model, contents, config)
            resp.embeddings = resp.embeddings[:-1]
            return resp

    emb, _ = _embedder(ShortModels())
    with pytest.raises(RuntimeError, match="2 texts"):
        emb.embed(["a", "b"])


def test_get_embedder_selects_gemini_with_settings(tmp_path):
    s = Settings(
        _env_file=None, embed_provider="gemini", gemini_api_key="test-key",
        gemini_embed_model="my-embed", gemini_embed_batch=7,
    )
    emb = get_embedder(s)
    assert isinstance(emb, GeminiEmbedder)
    assert emb.name == "gemini-my-embed" and emb.batch_size == 7


def test_get_embedder_gemini_without_key_is_a_clear_error():
    s = Settings(_env_file=None, embed_provider="gemini", gemini_api_key=None)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        get_embedder(s)


def test_default_provider_is_still_hash():
    assert isinstance(get_embedder(Settings(_env_file=None)), HashEmbedder)
