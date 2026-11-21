"""Gemini request config, checked offline with a fake client (no API key or network)."""

from types import SimpleNamespace

import pytest

from agent.llm_router import LLMError, LLMRouter
from shared.contracts import DraftAnswer
from shared.settings import Settings


def _router(tmp_path, **kw):
    s = Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", gemini_api_key="test-key", **kw)
    router = LLMRouter(s)
    seen = {}

    def generate_content(model, contents, config):
        seen.update(model=model, config=config)
        return SimpleNamespace(text='{"findings": [], "abstain": true}')

    router._gemini_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    return router, seen


def test_thinking_level_and_no_output_cap(tmp_path):
    router, seen = _router(tmp_path, gemini_thinking_level="low")
    assert router.complete("s", "u", DraftAnswer, provider="gemini").abstain
    cfg = seen["config"]
    assert cfg.thinking_config.thinking_level.name == "LOW"
    assert cfg.max_output_tokens is None and cfg.response_schema is DraftAnswer


def test_empty_level_uses_model_default(tmp_path):
    router, seen = _router(tmp_path, gemini_thinking_level="")
    router.complete("s", "u", DraftAnswer, provider="gemini")
    assert seen["config"].thinking_config is None


def test_bad_level_is_a_clear_error(tmp_path):
    router, _ = _router(tmp_path, gemini_thinking_level="turbo")
    with pytest.raises(LLMError, match="not a thinking level"):
        router.complete("s", "u", DraftAnswer, provider="gemini")
