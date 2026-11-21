# Requests from Je

## 2026-11-21 -> Sujitha: Gemini through Vertex AI with a gcloud login (no API key)
File: agent/llm_router.py (`LLMRouter._gemini`)
Why: our credits are on Google Cloud (Vertex AI), not on AI Studio. The plan is to authenticate with
`gcloud auth application-default login` (ADC) instead of an API key. Today `_gemini` raises
"GEMINI_API_KEY is not set" without a key and always passes `api_key=` to `genai.Client`. With a key the SDK goes
to Vertex express mode and ignores the project, so ADC is never used. (Checked offline with google-genai 3.6.1:
with `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` set, `genai.Client()`
with no key resolves to Vertex + that project; `genai.Client(api_key=...)` resolves to express mode with project None.)
Change: in `_gemini`, when the environment variable `GOOGLE_GENAI_USE_VERTEXAI` is "true" (case-insensitive):
- skip the `if not s.gemini_api_key` check;
- create the client without the key: `genai.Client(http_options=types.HttpOptions(timeout=...))`. The SDK reads
  `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from the environment and uses ADC.

Otherwise keep today's behaviour exactly (AI Studio key). No contract or settings change: environment variables
only, so `shared/settings.py` stays frozen. A test in `tests/test_llm_router*.py` with a monkeypatched
`genai.Client` can assert that no `api_key` is passed when the variable is set and that the key check is skipped.
Run with:
```bash
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<project-id> GOOGLE_CLOUD_LOCATION=global
```
Until then: Gemini drafting runs on the AI Studio key (free tier) or falls back to Ollama/extractive. Rithwik:
the planned Gemini embedder (`memory/embedder.py`) needs the same switch so the index can be built on Vertex.
Status: open
