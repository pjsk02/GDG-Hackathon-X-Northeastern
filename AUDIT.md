# Boilerplate Audit: Grounded Agent + Boston Open Data

**Date:** 2026-11-21 · **Auditor:** Claude (Opus 5.5) · **Scope:** every file in the project except `.venv/`, `data/` and the vendored A2UI test schemas.

> **Update, later on 2026-11-21:** the two projects described below have been **split into separate folders**.
> The grounded agent now lives in `D:\Projects\grounded-agent` (this folder), with its own `pyproject.toml`
> (`grounded-agent`), Makefile, `.env` and venv. The Boston open data pipeline stays in `D:\Projects\New folder`.
> Fixed since this audit: H1 (claim-vs-quote checks + quote-first UI), H2–H4 (28-case, ~100-chunk benchmark,
> recall@k, content scoring, split rejection metrics), M1 (no wildcard CORS), M2 (escaped Streamlit text),
> M3 (source names keep their root folder), M4 (agent compose only has a profile-gated, pinned Ollama),
> M5 (A2UI renderer vendored, works offline), L2 (deps split, lower bounds), L3, L5, L9, plus a crash where
> an embedding error took down `Agent.ask()`. M6 (Gemini never run) is still open: it needs an API key.

> **For the reviewer (Gemini):** this is a self-contained audit of a Python boilerplate. Every finding below
> was checked against the code. Where it says *Verified*, a script or test actually reproduced it.
> Please (1) challenge any finding you think is wrong, (2) point out anything missed, and (3) rank the fix
> list for a hackathon-style demo where reliability and "no hallucinations" are the pitch.

---

## 1. What this project is

The folder holds **two independent projects** that share config files but no code:

| | Grounded Agent (active) | Boston Open Data pipeline (skeleton) |
|---|---|---|
| Purpose | Answer questions over code, docs and media. Only claims backed by a **verbatim quote** from the indexed source are shown, with file + line or timestamp. | Harvest data.boston.gov (CKAN) into PostGIS and serve it via an API. |
| Storage | SQLite vector store (`data/memory.sqlite`) | Postgres/PostGIS (`db/`) |
| Code | `agent/`, `memory/`, `shared/`, `api/`, `ui/`, `eval/`, `tests/`, `samples/` | `db/001_schemas.sql`, `db/migrate.sh`, empty `ingest/` |
| State | Working end to end, 30/30 tests pass | Schemas + migration runner only. No harvest/load code |

Shared files: `docker-compose.yml` (services `db` and `ollama`), `Makefile` (one section each), `.env` / `.env.example`, `pyproject.toml`.

### Agent pipeline

```
ingest_code / ingest_docs / ingest_media  ->  Chunk (source, locator, text)
    -> VectorStore (SQLite, brute-force cosine; embedder: hash | Ollama EmbeddingGemma 2)
    -> retrieve top_k
    -> LLM router (extractive no-LLM baseline | Ollama Gemma 4 | Gemini) -> DraftAnswer (JSON-schema constrained)
    -> grounding: chunk_id must be in context, quote must appear verbatim, confidence >= MIN_CONFIDENCE
    -> AgentAnswer (findings + rejections + provider attempts)  ->  FastAPI / A2UI page / Streamlit / eval
```

- **Fallback chain:** if a provider errors, times out or returns invalid JSON, the next one in `LLM_FALLBACK` is tried. A failed provider is skipped for `LLM_COOLDOWN_S`. `extractive` never fails, so it goes last. A valid abstain does **not** trigger fallback.
- **Contract:** `shared/contracts.py` (Pydantic) is the single source of truth. `make schema` exports JSON Schema to `shared/schema/`.

### File map (agent side)

| File | Role |
|---|---|
| `shared/settings.py` | All config (pydantic-settings, reads `.env`) |
| `shared/contracts.py` | Chunk, DraftAnswer, Finding, Rejection, AgentAnswer, EvalCase, ... |
| `agent/llm_router.py` | `complete(system, user, Schema, provider)` for Ollama and Gemini. Warm-up and one retry for Ollama |
| `agent/grounding.py` | Verifies findings against the cited chunk |
| `agent/pipeline.py` | `Agent.ask()`, fallback chain, cooldown, `warm_up()`, extractive baseline, system prompt |
| `memory/embedder.py`, `memory/store.py` | Hash or Ollama embeddings. SQLite store tagged per embedder |
| `memory/chunking.py`, `memory/ingest_*.py`, `memory/common.py` | Line, paragraph, page and subtitle-cue chunking. Ingest CLIs |
| `api/main.py`, `api/a2ui.py`, `api/static/a2ui.html` | FastAPI (`/ask`, `/search`, `/sources`, `/health`, `/a2ui`). A2UI v1.0 surfaces rendered by Google's Lit renderer |
| `ui/app.py` | Streamlit demo: raw chunk, cited finding and confidence side by side |
| `eval/run.py`, `eval/cases.jsonl` | 12-case benchmark. Writes records, CSV, summary and chart |
| `tests/` | 30 offline tests: pipeline, grounding, fallback, A2UI schema validity, warm-up, Ollama retry |

---

## 2. Current status

### Verified working (2026-11-19 to 11-21)

| Check | Result |
|---|---|
| `pytest` | **30 / 30 pass** (~2 s, fully offline) |
| Eval, extractive baseline | 10/12 pass. Misses `doc-streetlight` and `code-cafe-fee` |
| Eval, Gemma 4 e4b on Ollama (RTX 4050, 6 GB) | **12/12 pass**, 0 errors, p50 1.7 s, p95 2.0 s |
| Stress test, 120 raw Ollama requests after a cold start | 0 anomalies |
| JSON Schema export vs. Pydantic models | No drift (all 7 match) |

### Environment as configured

- `.env`: `LLM_PROVIDER=ollama`, `LLM_FALLBACK=extractive`, `EMBED_PROVIDER=ollama`, `OLLAMA_URL=http://127.0.0.1:11434`, `GEMINI_API_KEY` empty.
- Ollama runs natively on Windows (not in Docker) with `gemma4:e4b` (6.6 GB) and `embeddinggemma-2:570m`.
- Docker Desktop is not running. A **native Postgres is already listening on 5432**, on all interfaces.
- The folder is **not a git repository**.

### Recent changes made during this session

1. **Startup warm-up.** API (background thread, status shown on `/health`), Streamlit (spinner) and eval load the embedder and the Ollama model first, with retries on load-time 500s. `OLLAMA_KEEP_ALIVE=30m`. `eval.run --no-warm-up` skips it.
2. **`127.0.0.1` instead of `localhost`** for Ollama. On Windows, `localhost` first tries IPv6 and added about 2 s to every request (measured: 2,085 ms vs 14 ms).
3. **One retry for fast Ollama failures** (truncated or invalid JSON, 5xx, malformed body), with `done_reason` and `eval_count` in the error. There is no retry on timeouts or connection errors. This was motivated by a one-off truncated reply (`{"`) that could not be reproduced in 130 later requests.

---

## 3. Findings

Severity: **High** means it undermines the core promise or will break the demo. **Medium** means a real defect with limited blast radius. **Low** covers hygiene and polish.

### High

**H1. Grounding verifies the quote, not the claim.** *Verified.*
`agent/grounding.py:43-56` checks that `evidence_quote` appears verbatim in the cited chunk. Nothing checks that `claim` is supported by that quote. A probe passed this through grounding as an **accepted** finding:
claim *"Potholes are never repaired; residents must fix them at their own cost."* with the real quote *"Potholes are repaired within two business days."*
Users see the claim in bold (`ui/app.py:89`, A2UI claim card), so a model can still mislead while "citing" real text. This is the project's central selling point.
*Fix options:* (a) show the verbatim quote as the primary answer and the claim as secondary; (b) require claim/quote lexical overlap above a threshold, cheap and offline; (c) add an entailment check (NLI model or a second LLM "does the quote support the claim?" call) and reject on "no" or "unsure". Add a test with a contradicting claim.

**H2. The eval cannot measure retrieval.** *Verified.*
The index has **4 chunks** and `top_k = 6` (`shared/settings.py:47`), so every question retrieves the entire corpus. `source_hit_rate = 100%` therefore says nothing about retrieval or the embedder. With 12 cases, one case is about 8 points, so differences between providers are mostly noise.
*Fix:* index a realistic corpus (hundreds or thousands of chunks), set `top_k` well below the corpus size, grow `cases.jsonl` to 30+ cases (the README already says 20-30), and add a retrieval-only metric (recall@k of the expected source before generation).

**H3. The eval only checks the source of a finding, not its content.** `eval/run.py:39-58`
A case passes if any finding cites a file whose name contains an expected substring. A wrong claim citing the right file passes. Combined with H1, "12/12" overstates answer quality.
*Fix:* add `expected_quote_contains` or `expected_answer_keywords` to `EvalCase` and score on them. Optionally add an LLM-as-judge field.

**H4. "hallucination_rate" counts something else.** `eval/run.py:19, 71-83`
The metric is grounding rejections divided by all drafted findings, which includes findings rejected only for **low confidence**. The extractive baseline's "22% hallucination" is really low-overlap lines being rejected by the 0.5 threshold, not fabrication. This will be challenged in a pitch.
*Fix:* split it into `fabrication_rate` (unknown chunk or quote not found) and `low_confidence_rate`, or rename it to `rejection_rate`.

### Medium

**M1. Any website can read the local API.** *Verified.* `api/main.py:49`
`CORSMiddleware(allow_origins=["*"])` on an unauthenticated server. A request from `Origin: https://evil.example` gets `access-control-allow-origin: *`. Any page open in the user's browser can call `http://127.0.0.1:8000/search` or `/ask` and read the indexed documents.
*Fix:* drop CORS entirely (the A2UI page is same-origin) or allow-list specific dev origins.

**M2. Unescaped model text in Streamlit Markdown.** `ui/app.py:89`, `ui/app.py:99`
`st.markdown(f"**{f.claim}**")` and the rejected-claims list render model output as Markdown. A claim can include links or images, for example a tracking-pixel image or a misleading link, and **rejected** claims are by definition untrusted. HTML is blocked (no `unsafe_allow_html`), but Markdown links and images are not. The A2UI path escapes correctly (`api/a2ui.py` `md_escape`).
*Fix:* escape Markdown, as `md_escape` does, or render with `st.text`.

**M3. Source names collide across ingest roots.** *Verified.* `memory/common.py:23`
`rel_source` makes the path relative to the root given on the CLI, so `dirA/readme.md` and `dirB/readme.md` both become `readme.md`. The second ingest silently `delete_source`s and replaces the first, and citations become ambiguous.
*Fix:* prefix with the root's name, or store paths relative to a fixed project or data root.

**M4. Docker stack conflicts with what is running.** *Verified.*
`make up` would try to bind **5432** (a native Postgres already listens there, `docker-compose.yml:12`) and **11434** (native Ollama, `docker-compose.yml:28`). Both binds fail. The README's model-pull instructions also assume the Ollama container.
*Fix:* pick one Ollama (native is already set up and faster to iterate on), drop or profile the `ollama` service (`profiles: ["docker-ollama"]`), and change `POSTGRES_PORT` or stop the native Postgres.

**M5. The A2UI page needs internet, but the fallback story is about offline.** `api/static/a2ui.html:63-69`
The renderer loads from `esm.sh` at runtime. The README's "Wi-Fi drop mid-demo still produces a cited answer" is true for the backend but not for this page, which will not render offline. The README notes the dependency, but the risk isn't flagged.
*Fix:* vendor the three pinned ESM bundles into `api/static/`, or keep the Streamlit UI as the offline demo path. Add SRI if staying on a CDN.

**M6. The Gemini backend has never run here.**
No API key is configured, so `agent/llm_router.py` `_gemini` (schema-constrained output via `response_schema`, `temperature=0` at `:155`) is covered only by mocked tests. Notes for newer models: **Gemini 4 Neon ignores custom sampling (fixed temperature 1.0)**, and its docs don't name `response_schema` explicitly. Run `python -m eval.run --compare extractive ollama gemini` once with a key before relying on it.

**M7. Prompt injection through indexed content.**
Retrieved chunk text goes straight into the user prompt (`agent/pipeline.py` `build_user_prompt`). An indexed document saying "ignore previous instructions, claim X" can steer the claim text. Quote verification limits the damage, but because of H1 the claim itself is unchecked.
*Fix:* fixing H1 is the main mitigation. Also delimit context clearly and tell the model that context is data.

### Low

- **L1. No version control.** The folder isn't a git repo, so there is no history or diff of this session's changes. Run `git init` and commit. `.gitignore` already excludes `.env`, `.venv`, `data/`.
- **L2. Unused and misplaced dependencies** (`pyproject.toml:10-23`). `sqlglot`, `psycopg`, `ckanapi`, `python-dotenv` are never imported (the first three are for the unbuilt open-data side). `pytest` is a runtime dependency (`:19`) and belongs in a `dev` extra. No dependency is version-pinned and there's no lock file, so reproducibility relies on `uv` resolving the same versions. `faster-whisper` is not in `[all]`.
- **L3. `ollama/ollama:latest` is unpinned** (`docker-compose.yml:24`).
- **L4. Broken Make targets.** `make ingest` and `make load` call `ingest.harvest` and `ingest.load`, which don't exist.
- **L5. Stale docstrings.** `api/__init__.py` says "serving the core schema" and `eval/__init__.py` describes the open-data side. Both packages now hold the agent's code.
- **L6. `VectorStore.sources()` ignores the embedder tag** (`memory/store.py:75`), unlike `count()` and `search()`. After switching embedders, the UI's "Indexed sources" lists files that aren't searchable until re-indexed.
- **L7. Unvalidated request inputs.** `AskRequest.k` (`shared/contracts.py:91`) is unbounded, a negative value effectively returns one chunk, `question` has no length cap, and `/ask` accepts any `provider` string (it fails into the fallback chain instead of returning a 422). The A2UI `reask` action validates the provider, but `/ask` doesn't.
- **L8. Thread safety.** One `sqlite3` connection with `check_same_thread=False` plus an unlocked vector cache and cooldown dict, shared across FastAPI's threadpool and the warm-up thread. This is fine at demo load. Use a lock or per-thread connections before real concurrency.
- **L9. `refine_locator` narrows line ranges only on an exact match** (`agent/grounding.py`). If the quote differs from the chunk in case or whitespace, it falls back to the whole chunk range. That's correct but less precise than it could be.
- **L10. Retry and warm-up timings.** The warm-up can take ~40 s from a cold GPU. The API answers during warm-up, but the first question blocks on the same load. `/health` shows `warm_up.status = pending` meanwhile, which the UI could surface.

---

## 4. What is solid

- **One contract file** (`shared/contracts.py`). Schema export has no drift. The API, UI, eval and A2UI all consume `AgentAnswer`.
- **Source and locator come from the store, never the model**, and unknown chunk ids are rejected.
- **The fallback chain is well designed:** a valid abstain doesn't fall back (no shopping for a willing model), cooldown avoids repeated timeouts, every attempt is recorded, and it's well tested.
- **A2UI output** is built in code after grounding, Markdown-escaped, source chunks are fenced, and messages are validated against the official v1.0 schemas in tests.
- **It runs offline from zero setup** with the hash embedder and extractive provider. The tests need no network.
- **Locators** are precise (line ranges, PDF pages, `HH:MM:SS` windows for transcripts).

---

## 5. Recommended fix order (demo-focused)

| # | Item | Effort | Why first |
|---|---|---|---|
| 1 | H1: claim-vs-quote check (start with lexical overlap and quote-first display) | S-M | It is the product's core promise |
| 2 | H2 + H3: real corpus, `top_k` below corpus size, 30+ cases, content-level scoring, recall@k | M | Without this the eval numbers can't support any claim |
| 3 | H4: split or rename hallucination_rate | XS | Avoids a credibility hit in the pitch |
| 4 | M1 + M2: remove `*` CORS, escape Streamlit Markdown | XS | Cheap security wins |
| 5 | M4 + M5: settle on native Ollama, fix port conflicts, vendor A2UI JS or use Streamlit offline | S | Demo-day reliability |
| 6 | M6: one real Gemini eval run (Hydrogen, optionally Neon) | XS + key | Last untested path |
| 7 | M3, L1-L10 | S each | Hygiene |

## 6. Questions for the reviewer

1. For H1, is a lightweight lexical or NLI check enough, or should the agent switch to a quote-first answer format where the model only selects spans?
2. Is brute-force cosine search over SQLite adequate up to the expected corpus size, or should it move to `sqlite-vec` or pgvector now that Postgres is available?
3. Should the Boston open-data pipeline feed the agent (CKAN datasets as indexed docs), or stay a separate deliverable?

## 7. How to reproduce

```bash
uv pip install -e ".[all]"
python -m memory.ingest_docs samples/docs --reset && python -m memory.ingest_code samples/code && python -m memory.ingest_media samples/media
pytest -q
python -m eval.run --compare extractive ollama
```
