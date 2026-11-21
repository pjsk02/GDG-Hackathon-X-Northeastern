"""Gemini request config, checked offline with a fake client (no API key or network)."""

from types import SimpleNamespace

import pytest

import agent.llm_router as llm_router
from agent.llm_router import LLMError, LLMRouter
from shared.contracts import DraftAnswer, SentinelDraft
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


def _scripted_router(tmp_path, responses, **kw):
    s = Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", gemini_api_key="test-key", **kw)
    router = LLMRouter(s)
    queue = list(responses)
    calls = []

    def generate_content(model, contents, config):
        calls.append({"model": model, "contents": contents, "config": config})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item)

    router._gemini_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    return router, calls


def test_sentinel_draft_structured_output(tmp_path):
    payload = (
        '{"reply_language": "en", "refused": false, "refusal_reason": "", '
        '"citations": [{"ticket_id": "TKT-00001", "evidence_quote": "Restarted the VPN gateway."}], '
        '"draft_reply": "We restarted the VPN gateway.", "briefing": "User cannot connect to VPN."}'
    )
    router, calls = _scripted_router(tmp_path, [payload], gemini_model="gemini-3.5-flash-lite")
    draft = router.complete("s", "u", SentinelDraft, provider="gemini")
    assert isinstance(draft, SentinelDraft)
    assert not draft.refused and draft.citations[0].ticket_id == "TKT-00001"
    assert calls[0]["config"].response_schema is SentinelDraft


def test_transient_503_retries_once(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_router.time, "sleep", lambda _: None)

    class _Fake503(Exception):
        code = 503

    router, calls = _scripted_router(tmp_path, [_Fake503("high demand"), '{"findings": [], "abstain": true}'])
    assert router.complete("s", "u", DraftAnswer, provider="gemini").abstain
    assert len(calls) == 2


def test_invalid_json_retries_once(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_router.time, "sleep", lambda _: None)
    router, calls = _scripted_router(tmp_path, ['{"findings": ', '{"findings": [], "abstain": true}'])
    assert router.complete("s", "u", DraftAnswer, provider="gemini").abstain
    assert len(calls) == 2


@pytest.mark.parametrize("code", [400, 403, 404, 504])
def test_non_transient_errors_are_not_retried(tmp_path, monkeypatch, code):
    monkeypatch.setattr(llm_router.time, "sleep", lambda _: None)

    class _FakeErr(Exception):
        pass

    err = _FakeErr(f"HTTP {code}")
    err.code = code
    router, calls = _scripted_router(tmp_path, [err, '{"findings": [], "abstain": true}'])
    with pytest.raises(LLMError):
        router.complete("s", "u", DraftAnswer, provider="gemini")
    assert len(calls) == 1
