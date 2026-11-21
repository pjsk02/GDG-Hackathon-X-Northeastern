"""Fallback chain: offline, using a scripted router instead of real models."""

from pathlib import Path

import pytest

from agent.llm_router import LLMError
from agent.pipeline import Agent
from memory import ingest_docs
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from shared.contracts import DraftAnswer
from shared.settings import Settings

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
QUESTION = "How quickly are reported potholes repaired?"


class ScriptedRouter:
    """Each provider maps to an exception to raise, a raw JSON string to validate, or a DraftAnswer."""

    def __init__(self, behaviour: dict):
        self.behaviour = behaviour
        self.calls: list[str] = []

    def model_name(self, provider=None):
        return f"{provider}-model"

    def complete(self, system, user, schema, provider=None):
        self.calls.append(provider)
        b = self.behaviour.get(provider, LLMError(f"no backend {provider}"))
        if isinstance(b, Exception):
            raise b
        if isinstance(b, str):
            return schema.model_validate_json(b)
        return b


def make_agent(tmp_path, router, **overrides) -> Agent:
    settings = Settings(_env_file=None, llm_provider="gemini", llm_fallback="ollama,extractive",
                        embed_provider="hash", memory_path=tmp_path / "m.sqlite", **overrides)
    store = VectorStore(settings.memory_path, HashEmbedder())
    store.add(ingest_docs.to_chunks(SAMPLES / "docs/street_services.md", "street_services.md"))
    return Agent(settings=settings, store=store, router=router)


def test_chain_order_and_dedupe(tmp_path):
    agent = make_agent(tmp_path, ScriptedRouter({}))
    assert agent.provider_chain() == ["gemini", "ollama", "extractive"]
    assert agent.provider_chain("ollama") == ["ollama", "extractive"]
    assert agent.provider_chain("gemini", fallback=False) == ["gemini"]


def test_falls_through_to_extractive(tmp_path):
    router = ScriptedRouter({"gemini": LLMError("timeout"), "ollama": LLMError("connection refused")})
    ans = make_agent(tmp_path, router).ask(QUESTION)
    assert ans.provider == "extractive" and ans.fell_back and ans.error is None
    assert [(a.provider, a.ok) for a in ans.attempts] == [("gemini", False), ("ollama", False), ("extractive", True)]
    assert ans.findings  # still a grounded, cited answer


def test_invalid_json_triggers_fallback(tmp_path):
    router = ScriptedRouter({"gemini": '{"findings": "not a list"}', "ollama": DraftAnswer(abstain=True)})
    ans = make_agent(tmp_path, router).ask(QUESTION)
    assert ans.provider == "ollama" and ans.fell_back
    assert ans.attempts[0].error


def test_valid_abstain_does_not_fall_back(tmp_path):
    router = ScriptedRouter({"gemini": DraftAnswer(abstain=True)})
    ans = make_agent(tmp_path, router).ask(QUESTION)
    assert ans.provider == "gemini" and not ans.fell_back and ans.abstained
    assert router.calls == ["gemini"]


def test_cooldown_skips_failed_provider(tmp_path):
    router = ScriptedRouter({"gemini": LLMError("down"), "ollama": DraftAnswer(abstain=True)})
    agent = make_agent(tmp_path, router, llm_cooldown_s=60)
    agent.ask(QUESTION)
    ans = agent.ask(QUESTION)
    assert router.calls == ["gemini", "ollama", "ollama"]  # gemini not retried the second time
    assert ans.attempts[0].skipped
    assert "gemini" in agent.cooling_down()


def test_recovery_clears_cooldown(tmp_path):
    router = ScriptedRouter({"gemini": LLMError("down"), "ollama": DraftAnswer(abstain=True)})
    agent = make_agent(tmp_path, router, llm_cooldown_s=0)
    agent.ask(QUESTION)
    router.behaviour["gemini"] = DraftAnswer(abstain=True)
    assert agent.ask(QUESTION).provider == "gemini"


def test_no_fallback_reports_error(tmp_path):
    router = ScriptedRouter({"gemini": LLMError("rate limited")})
    ans = make_agent(tmp_path, router).ask(QUESTION, fallback=False)
    assert ans.abstained and not ans.fell_back
    assert ans.error == "gemini: rate limited"


def test_retrieval_failure_returns_an_error_answer(tmp_path):
    # e.g. Ollama's embedding runner crashed: ask() must answer with an error, not raise (it used to
    # crash the whole eval run).
    agent = make_agent(tmp_path, ScriptedRouter({}))

    def boom(*a, **k):
        raise RuntimeError("500 Server Error for url: /api/embed")

    agent.store.search = boom
    ans = agent.ask(QUESTION)
    assert ans.abstained and not ans.findings
    assert ans.error.startswith("retrieval failed")


@pytest.mark.parametrize("provider", ["gemini"])
def test_explicit_provider_is_tried_even_if_cooling(tmp_path, provider):
    router = ScriptedRouter({"gemini": LLMError("down")})
    agent = make_agent(tmp_path, router, llm_cooldown_s=60)
    agent.ask(QUESTION)
    agent.ask(QUESTION, provider=provider, fallback=False)
    assert router.calls.count("gemini") == 2  # a single-provider chain never skips
