"""LLMRouter Gemini Vertex AI (ADC) vs AI Studio key client construction tests (offline).

Owner: D (Sujitha). Fulfils docs/requests/Je.md ("Gemini through Vertex AI with a gcloud login").
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google import genai

from agent.llm_router import LLMError, LLMRouter
from shared.contracts import DraftAnswer
from shared.settings import Settings


def _patch_client(monkeypatch):
    seen: dict[str, object] = {}

    def fake_client(**kwargs):
        seen["client_kwargs"] = kwargs

        def generate_content(model, contents, config):
            seen["model"] = model
            return SimpleNamespace(text='{"findings": [], "abstain": true}')

        return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))

    monkeypatch.setattr(genai, "Client", fake_client)
    return seen


@pytest.mark.parametrize("flag", ["true", "TRUE", "True", " true "])
def test_vertex_ai_env_skips_api_key_and_uses_adc(tmp_path, monkeypatch, flag):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", flag)
    seen = _patch_client(monkeypatch)
    s = Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", gemini_api_key=None)
    ans = LLMRouter(s).complete("s", "u", DraftAnswer, provider="gemini")
    assert ans.abstain
    kwargs = seen["client_kwargs"]
    assert "api_key" not in kwargs
    assert "http_options" in kwargs


def test_vertex_ai_env_omits_api_key_even_when_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    seen = _patch_client(monkeypatch)
    s = Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", gemini_api_key="unused-key")
    LLMRouter(s).complete("s", "u", DraftAnswer, provider="gemini")
    assert "api_key" not in seen["client_kwargs"]


@pytest.mark.parametrize("flag", [None, "", "false", "0"])
def test_ai_studio_requires_api_key_when_vertex_disabled(tmp_path, monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    else:
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", flag)
    s = Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", gemini_api_key=None)
    with pytest.raises(LLMError, match="GEMINI_API_KEY is not set"):
        LLMRouter(s).complete("s", "u", DraftAnswer, provider="gemini")


def test_ai_studio_passes_api_key_when_vertex_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    seen = _patch_client(monkeypatch)
    s = Settings(_env_file=None, memory_path=tmp_path / "m.sqlite", gemini_api_key="ai-studio-key")
    LLMRouter(s).complete("s", "u", DraftAnswer, provider="gemini")
    assert seen["client_kwargs"]["api_key"] == "ai-studio-key"
    assert "http_options" in seen["client_kwargs"]
