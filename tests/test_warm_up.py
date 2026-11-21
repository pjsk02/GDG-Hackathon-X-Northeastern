"""Warm-up loads local models up front, retries Ollama's load-time 500s, and never raises."""

import requests

import agent.llm_router as llm_router
import memory.embedder as embedder_mod
from agent.llm_router import LLMRouter
from agent.pipeline import Agent
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from shared.settings import Settings


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code, self._payload = status, payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")

    def json(self) -> dict:
        return self._payload


def _settings(tmp_path, **kw) -> Settings:
    kw = {"llm_provider": "ollama", "llm_fallback": "extractive", **kw}
    return Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", **kw)


def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm_router.time, "sleep", lambda s: None)
    monkeypatch.setattr(embedder_mod.time, "sleep", lambda s: None)


def test_router_retries_until_model_loads(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def post(url, json, timeout):
        calls.append(json)
        return FakeResponse(500 if len(calls) < 3 else 200)

    monkeypatch.setattr(llm_router.requests, "post", post)
    LLMRouter(_settings(tmp_path)).warm_up()
    assert len(calls) == 3
    assert calls[0]["messages"] == [] and calls[0]["keep_alive"] == "30m"


def test_agent_warm_up_reports_failure_without_raising(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    monkeypatch.setattr(llm_router.requests, "post", lambda *a, **k: FakeResponse(500))
    s = _settings(tmp_path)
    agent = Agent(settings=s, store=VectorStore(s.memory_path, HashEmbedder()))
    status = agent.warm_up()
    assert set(status) == {"ollama"}  # hash embedder and extractive need no warm-up
    assert "warm-up failed" in status["ollama"]


def test_non_ollama_chain_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_router.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    s = _settings(tmp_path, llm_provider="extractive")
    agent = Agent(settings=s, store=VectorStore(s.memory_path, HashEmbedder()))
    assert agent.warm_up() == {}


def test_ollama_embedder_warm_up_retries(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def post(url, json, timeout):
        calls.append(json)
        return FakeResponse(500) if len(calls) == 1 else FakeResponse(200, {"embeddings": [[1.0, 0.0]]})

    monkeypatch.setattr(embedder_mod.requests, "post", post)
    embedder_mod.OllamaEmbedder("http://127.0.0.1:11434", "embeddinggemma-2:570m", keep_alive="30m").warm_up()
    assert len(calls) == 2 and calls[1]["keep_alive"] == "30m"
