# Rithwik - progress log (role C)

## Step 1 - Gemini embedder (F4)

**Built**
- `GeminiEmbedder` in memory/embedder.py, returned by `get_embedder` when `EMBED_PROVIDER=gemini`.
  - google-genai 3.6.1 `client.models.embed_content(model, contents, config=EmbedContentConfig(task_type=...))`.
  - `RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` when `is_query=True`.
  - Batches of `GEMINI_EMBED_BATCH` (64), model `GEMINI_EMBED_MODEL` (gemini-embedding-001), timeout `GEMINI_TIMEOUT_S`.
  - Unit-normalized float32 rows; `name = "gemini-<model>"` so the store keeps vectors per embedder.
  - Retries HTTP 429, 5xx and network errors (httpx2 or httpx `TransportError`) with exponential backoff
    (2 s doubling, capped at 60 s, 6 retries). Other 4xx (400, 403) fail at once.
  - Missing `GEMINI_API_KEY` raises a clear `ValueError` from `get_embedder`.

**Files**: memory/embedder.py, tests/test_embedder_gemini.py (new).

**Verified**
- `uv run pytest -q tests/test_embedder_gemini.py` -> 14 passed (fake client, no network).
- `uv run pytest -q` -> 70 passed.
- `EMBED_PROVIDER=hash python -m sentinel.ingest_tickets --reset --limit 50 --memory <tmp>` -> 50 chunks indexed.
- `scripts/check_ownership.py` -> OK.

**Open issues**
- Gemini smoke index NOT yet run: the API key I have gets `403 PERMISSION_DENIED` from
  generativelanguage.googleapis.com on every call (even listing models). Checking with the organizers.
  Rerun once a working key is in .env: `EMBED_PROVIDER=gemini python -m sentinel.ingest_tickets --reset --limit 50`.

**For teammates**
- Nothing changes for you: default `EMBED_PROVIDER=hash` still returns `HashEmbedder`.

## Step 2 - Demo index and cross-lingual check (B1) - PARTIAL (Gemini part waits on a working key)

**Built**
- eval/crosslingual_check.py: for the 958 German VALIDATION tickets, searches the kb_train index (skipping the ticket
  itself) and reports `share_topk_english`, `top1_english`, `top1_same_queue`, `top1_score_mean` per embedder.
  Writes data/eval/crosslingual.json. Holdout never read.
  - Each embedder has its own index file (chunk ids are ticket ids): gemini -> data/sentinel.sqlite (demo index),
    others -> data/eval/crosslingual_<provider>.sqlite, built on demand for hash (~5 s).
  - Queries are embedded in batches (64 per Gemini call), so the gemini run costs ~15 calls, not 958.
- memory/store.py: new `VectorStore.vectors()` -> (ids, matrix) for batch scoring. No existing behaviour changed.

**Numbers so far (k=5, 958 German validation tickets)**

| embedder | share top-5 English | top-1 English | top-1 same queue | mean top-1 score |
|---|---|---|---|---|
| hash | 0.186 | 0.181 | 0.568 | 0.688 |
| gemini | pending key | | | |

**Files**: eval/crosslingual_check.py (new), tests/test_crosslingual_check.py (new), memory/store.py.

**Verified**: `pytest -q tests/test_crosslingual_check.py` -> 4 passed; `python -m eval.crosslingual_check --providers hash`.

**Still to do once the key works**
1. Check the embedding rate limit, then `EMBED_PROVIDER=gemini make sentinel-index` (log time + throttling).
2. `python -m eval.crosslingual_check` (hash vs gemini) and fill in the table.
3. Upload data/sentinel.sqlite and put the team-only link here.
