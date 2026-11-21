# Grounded Agent scaffold

Ask questions over code, documents and media; get back only claims that are **verified against a verbatim quote** in the indexed source, with file + line or timestamp. Anything the model can't back up is rejected and shown as "caught".

Everything runs offline by default (hash embeddings + an extractive no-LLM baseline), so the pipeline works before any model or key is set up. Switch to real models in `.env`.

```
ingest_*  ->  Chunk  ->  VectorStore (SQLite)  ->  retrieve  ->  LLM (DraftAnswer)  ->  grounding  ->  AgentAnswer
                                                                                         |
                                                                       api/  ui/  eval/ all consume this
```

## Layout

| Path | What it is |
|---|---|
| `shared/contracts.py` | **The JSON contract.** Every module imports from here. `make schema` writes JSON Schema to `shared/schema/` for non-Python clients. |
| `shared/settings.py` | All config, read from `.env`. |
| `agent/llm_router.py` | One `complete(system, user, Schema)` call for Ollama (local) and Gemini (AI Studio), always returning a validated Pydantic object. |
| `agent/grounding.py` | Rejects findings whose quote isn't in the cited chunk, that cite unknown chunks, or that fall below `MIN_CONFIDENCE`. Source and line come from the store, never the model. |
| `agent/pipeline.py` | `Agent().ask(question)`. Put kickoff domain logic in `DOMAIN_INSTRUCTIONS`. |
| `memory/` | Embedder (hash / Ollama EmbeddingGemma 2), SQLite vector store, and `ingest_code.py`, `ingest_docs.py`, `ingest_media.py`. |
| `eval/run.py`, `eval/cases.jsonl` | Benchmark: pass rate, abstain accuracy, source precision, hallucination rate, latency, plus `chart.png` and `results.csv`. |
| `api/main.py` | FastAPI: `/ask`, `/search`, `/sources`, `/health`, plus `/a2ui` (page) and `/a2ui/agent` (A2UI messages). |
| `api/a2ui.py`, `api/static/a2ui.html` | A2UI v1.0: turns a grounded `AgentAnswer` into A2UI surfaces; the page renders them with Google's official Lit renderer. |
| `ui/app.py` | Streamlit demo: raw input, cited finding and confidence side by side. |
| `samples/` | Tiny synthetic corpus so everything runs end to end. Replace at kickoff. |
| `eval/cases_repo.jsonl` | 28-case stand-in benchmark over this repo's own code (`make index-bench`, `make eval-bench`), so retrieval is actually tested (~100 chunks, `TOP_K=5`). |
| `tools/vendor_a2ui.py` | Mirrors the A2UI renderer into `api/static/vendor/` so the A2UI page works offline. |
| `docker-compose.yml` | Optional Ollama container (`make ollama-up`), for machines without native Ollama. |

The Boston open data pipeline (CKAN -> PostGIS) that used to share this folder now lives in its own project, `D:\Projects\New folder`.

## Setup

```bash
uv venv --python 3.12
```

```bash
uv pip install -e ".[all]"
```

(`[all]` = Gemini, Streamlit UI, plots, PDF support and the test tools. Audio transcription is separate: `.[media]`.)

```bash
cp .env.example .env
```

Then smoke test:

```bash
make index-samples
```

```bash
make ask Q="How quickly are reported potholes repaired?"
```

```bash
make eval
```

```bash
make ui
```

## A2UI UI

`make api`, then open http://127.0.0.1:8000/a2ui (or `/`, which redirects there).

The agent answers in [A2UI v1.0](https://a2ui.org/specification/v1.0-a2ui/), Google's open agent-to-UI protocol: a
list of `createSurface` + `updateComponents` messages using the Basic Catalog. Any A2UI renderer (web, Flutter,
Android, iOS) can draw the same response.

- **Built in code, not by the model.** `api/a2ui.py` builds the surface from the answer *after* grounding, so only
  verified text reaches the screen. Body text is Markdown-escaped and source chunks are fenced.
- **One surface per answer.** Each verified finding is a card (claim, quote, source and line, confidence).
  Abstentions, rejections and fallbacks are shown too.
- **Actions:** `show_source {chunk_id}` opens the cited chunk; `reask {question, provider}` asks again with
  Gemma 4 or Gemini and stacks the result for side-by-side comparison.
- **Renderer:** `@a2ui/lit` + `@a2ui/web_core` 0.15.0 and `@a2ui/markdown-it` 0.2.2, mirrored from esm.sh into
  `api/static/vendor/` (no Node build) and served locally, so the page works with no internet.
  Re-mirror after bumping a version: `make vendor`.
- **Tests:** `tests/test_a2ui.py` validates every message against the official schemas in `tests/a2ui_v1_0/`.

## Switching to real models

Local (offline), with native Ollama (or `make ollama-up` and prefix with `docker compose exec ollama`):

```bash
ollama pull gemma4:e4b
```

```bash
ollama pull embeddinggemma-2:570m
```

Then in `.env`: `LLM_PROVIDER=ollama`, `EMBED_PROVIDER=ollama`. **Re-index after changing the embedder** (vectors are tagged per embedder and won't mix).

Models are loaded at startup (`WARM_UP=true`) and kept for `OLLAMA_KEEP_ALIVE` (30m). On demo day set `OLLAMA_KEEP_ALIVE=-1m` so they never unload.

Gemini: set `GEMINI_API_KEY` (default model `gemini-4-hydrogen`; `gemini-3.5-flash-lite` is the cheaper free-tier option), then `LLM_PROVIDER=gemini`, or pick per request (`provider` field on `/ask`, the UI dropdown, or `--provider`).

### Fallback chain

If the chosen provider errors, times out, is rate-limited or returns invalid JSON, the agent tries the next one in `LLM_FALLBACK` (default `ollama,extractive`). With `LLM_PROVIDER=gemini` that gives **gemini -> local Gemma -> extractive**, so a Wi-Fi drop mid-demo still produces a cited answer. A failed provider is skipped for `LLM_COOLDOWN_S` (60 s) so later requests don't each wait out the timeout. `GEMINI_TIMEOUT_S` (30 s) caps a hung cloud call.

A valid answer that abstains, or whose claims all fail grounding, does **not** trigger fallback.

Every `AgentAnswer` records `provider` (who actually answered), `fell_back`, and `attempts` (each step with its error and latency). The UI shows "answered by X instead" when it happens, and `/health` lists providers that are cooling down. The UI checkbox, `"fallback": false` on `/ask`, and `eval.run` (off unless `--fallback`) let you pin one provider.

Compare providers for the pitch:

```bash
python -m eval.run --compare extractive ollama gemini
```

## At kickoff

1. Drop the dataset somewhere and index it: `make index-docs DIR=...` / `index-code` / `index-media`.
2. Write the domain prompt into `DOMAIN_INSTRUCTIONS` in `agent/pipeline.py`.
3. Replace `eval/cases.jsonl` with 20-30 domain questions, including a few that should abstain.
4. If the JSON contract must change, change `shared/contracts.py` only, then `make schema`.

## Tests

```bash
make test
```
