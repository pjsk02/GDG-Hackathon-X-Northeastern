"""Ollama backend: one quick retry on truncated/invalid output or 5xx; no retry on timeouts."""

import json

import pytest
import requests

import agent.llm_router as llm_router
from agent.llm_router import LLMError, LLMRouter
from shared.contracts import DraftAnswer
from shared.settings import Settings

VALID = '{"findings": [], "abstain": true}'


class Resp:
    def __init__(self, status: int = 200, content: str | None = VALID, done_reason: str = "stop"):
        self.status_code = status
        self._body = {"message": {"content": content}, "done_reason": done_reason, "eval_count": 2}
        self.text = json.dumps(self._body) if status < 400 else "model is loading"

    def json(self) -> dict:
        return self._body


def _router(tmp_path) -> LLMRouter:
    return LLMRouter(Settings(_env_file=None, memory_path=tmp_path / "m.sqlite"))


def _serve(monkeypatch, *responses):
    """Each call to requests.post returns (or raises) the next item."""
    queue, calls = list(responses), []

    def post(*a, **k):
        calls.append(k)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm_router.requests, "post", post)
    return calls


def test_truncated_reply_is_retried_once(tmp_path, monkeypatch):
    calls = _serve(monkeypatch, Resp(content='{"'), Resp())
    assert _router(tmp_path).complete("s", "u", DraftAnswer, provider="ollama").abstain
    assert len(calls) == 2


def test_server_error_is_retried_once(tmp_path, monkeypatch):
    calls = _serve(monkeypatch, Resp(status=500), Resp())
    _router(tmp_path).complete("s", "u", DraftAnswer, provider="ollama")
    assert len(calls) == 2


def test_two_bad_replies_raise_with_diagnostics(tmp_path, monkeypatch):
    _serve(monkeypatch, Resp(content='{"'), Resp(content='{"', done_reason="length"))
    with pytest.raises(LLMError) as exc:
        _router(tmp_path).complete("s", "u", DraftAnswer, provider="ollama")
    assert "done_reason=length" in str(exc.value) and "content='{\"'" in str(exc.value)


@pytest.mark.parametrize("err", [requests.Timeout("read timed out"), requests.ConnectionError("refused")])
def test_timeouts_and_connection_errors_are_not_retried(tmp_path, monkeypatch, err):
    calls = _serve(monkeypatch, err, Resp())
    with pytest.raises(LLMError):
        _router(tmp_path).complete("s", "u", DraftAnswer, provider="ollama")
    assert len(calls) == 1


def test_client_errors_are_not_retried(tmp_path, monkeypatch):
    calls = _serve(monkeypatch, Resp(status=404), Resp())
    with pytest.raises(LLMError, match="HTTP 404"):
        _router(tmp_path).complete("s", "u", DraftAnswer, provider="ollama")
    assert len(calls) == 1
