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
