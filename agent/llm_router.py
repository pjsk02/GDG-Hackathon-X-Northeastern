"""One call signature for every model backend, always returning a validated Pydantic object.

    router = LLMRouter(settings)
    draft = router.complete(system, user, DraftAnswer)                    # default provider
    draft = router.complete(system, user, DraftAnswer, provider="gemini") # route per call

Backends:
    ollama  local (e.g. Gemma), offline, uses Ollama's JSON-schema structured output
    gemini  Google AI Studio via the google-genai SDK (pip install -e ".[gemini]")
"""

import time
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from shared.settings import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class _TransientLLMError(LLMError):
    """A fast failure worth one immediate retry: truncated/invalid JSON, HTTP 5xx, an error body.
    Timeouts and connection errors are NOT transient here: retrying would just double the wait."""


class LLMRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._gemini_client = None

    def model_name(self, provider: str | None = None) -> str:
        provider = provider or self.settings.llm_provider
        return {
            "ollama": self.settings.ollama_model,
            "gemini": self.settings.gemini_model,
        }.get(provider, provider)

    def complete(self, system: str, user: str, schema: type[T], provider: str | None = None) -> T:
        provider = provider or self.settings.llm_provider
        if provider == "ollama":
            return self._ollama(system, user, schema)
        if provider == "gemini":
            return self._gemini(system, user, schema)
        raise LLMError(f"LLMRouter has no backend for provider {provider!r}")

    def warm_up(self, provider: str | None = None, attempts: int = 3) -> None:
        """Load the model before the first real request. Only Ollama has a cold start worth paying
        up front; it can also return a 500 while still loading, so retry a few times."""
        provider = provider or self.settings.llm_provider
        if provider != "ollama":
            return
        s = self.settings
        last: Exception | None = None
        for i in range(attempts):
            try:
                # An empty message list makes Ollama load the model without generating anything.
                r = requests.post(
                    f"{s.ollama_url}/api/chat",
                    json={"model": s.ollama_model, "messages": [], "keep_alive": s.ollama_keep_alive},
                    timeout=(5, s.request_timeout_s),
                )
                r.raise_for_status()
                return
            except requests.RequestException as e:
                last = e
                if i < attempts - 1:
                    time.sleep(2 * (i + 1))
        raise LLMError(f"Ollama warm-up failed ({s.ollama_url}, model={s.ollama_model}): {last}")

    # -- backends ----------------------------------------------------------

    def _ollama(self, system: str, user: str, schema: type[T], attempts: int = 2) -> T:
        # Gemma 4 on Ollama very occasionally stops after a couple of tokens (seen once: content
        # '{"'), and returns 500s while a model is (re)loading. Both are one-offs, so one quick
        # retry here beats dropping straight to the fallback provider.
        for i in range(attempts):
            try:
                return self._ollama_once(system, user, schema)
            except _TransientLLMError:
                if i == attempts - 1:
                    raise
        raise AssertionError("unreachable")

    def _ollama_once(self, system: str, user: str, schema: type[T]) -> T:
        s = self.settings
        try:
            r = requests.post(
                f"{s.ollama_url}/api/chat",
                json={
                    "model": s.ollama_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": schema.model_json_schema(),
                    "stream": False,
                    "think": s.ollama_think,
                    "keep_alive": s.ollama_keep_alive,
                    "options": {"temperature": 0},
                },
                timeout=(5, s.request_timeout_s),  # (connect, read): a dead server fails in 5 s
            )
        except requests.RequestException as e:
            raise LLMError(f"Ollama request failed ({s.ollama_url}, model={s.ollama_model}): {e}") from e

        where = f"({s.ollama_url}, model={s.ollama_model})"
        if r.status_code >= 500:
            raise _TransientLLMError(f"Ollama HTTP {r.status_code} {where}: {r.text[:200]}")
        if r.status_code >= 400:
            raise LLMError(f"Ollama HTTP {r.status_code} {where}: {r.text[:200]}")
        try:
            body = r.json()
            content = body["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise _TransientLLMError(f"Ollama returned an unexpected body {where}: {r.text[:200]}") from None
        try:
            return schema.model_validate_json(content)
        except ValidationError as e:
            # done_reason/eval_count tell a truncated reply ("length", few tokens) from a bad one.
            raise _TransientLLMError(
                f"Ollama returned invalid {schema.__name__} JSON {where} "
                f"(done_reason={body.get('done_reason')}, eval_count={body.get('eval_count')}, "
                f"content={content[:120]!r}): {e.errors()[0]['msg'] if e.errors() else e}"
            ) from e

    def _gemini(self, system: str, user: str, schema: type[T]) -> T:
        s = self.settings
        if not s.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise LLMError('google-genai not installed: pip install -e ".[gemini]"') from e

        if self._gemini_client is None:
            self._gemini_client = genai.Client(
                api_key=s.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(s.gemini_timeout_s * 1000)),  # milliseconds
            )
        thinking = None
        if s.gemini_thinking_level:
            try:
                thinking = types.ThinkingConfig(thinking_level=types.ThinkingLevel[s.gemini_thinking_level.upper()])
            except KeyError as e:
                raise LLMError(f"GEMINI_THINKING_LEVEL={s.gemini_thinking_level!r} is not a thinking level") from e
        try:
            # No max_output_tokens: a cap can cut the JSON off mid-object (thinking tokens count toward it).
            resp = self._gemini_client.models.generate_content(
                model=s.gemini_model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                    thinking_config=thinking,
                ),
            )
        except Exception as e:  # SDK raises several error types
            raise LLMError(f"Gemini request failed (model={s.gemini_model}): {e}") from e
        if not resp.text:  # e.g. blocked by a safety filter
            raise LLMError(f"Gemini returned no text (model={s.gemini_model})")
        return schema.model_validate_json(resp.text)
