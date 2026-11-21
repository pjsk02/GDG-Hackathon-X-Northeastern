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

## Step 3 - Ticket store on SQLite

**Built**
- sentinel/ticket_store.py now stores tickets in SQLite at `TICKET_STORE_PATH` (default data/tickets.sqlite).
  Every contract function keeps its name, arguments and return type; `TicketRecord` is unchanged.
  - `TicketStore(path)` class does the work; the module functions delegate to one shared store per process.
  - Thread-safe: one connection behind a lock, writes in `BEGIN IMMEDIATE`, WAL mode and a 30 s busy timeout so
    Streamlit and the API can share the file.
  - Ids stay `SD-1001`, `SD-1002`, ...; `reset()` empties the table and ids restart at SD-1001.
  - Results stored as `SentinelResult.model_dump_json()` and loaded back with `model_validate_json`.
  - `list_tickets` is newest first, ties broken by insertion order.
  - `save_result` / `set_status` on an unknown id raise `KeyError` (same as the in-memory version).
  - Under pytest the module functions use a temp file, so `pytest` (incl. the contract test's `reset()`) never wipes
    the demo store. `ticket_store.configure(path)` points them at a specific file.

**Files**: sentinel/ticket_store.py, tests/test_ticket_store.py (new).

**Verified**
- `pytest -q tests/test_ticket_store.py` -> 13 passed: add/get, list by status, set_status, save_result round trip,
  persistence across two store instances, two open instances, reset, 8 threads x 25 tickets concurrent writes,
  two instances writing concurrently, configure().
- `pytest -q` -> 86 passed (run 3 times, no flakes). data/tickets.sqlite is not created by the tests.

**For teammates (Kaushik)**
- Nothing to change: keep calling `ticket_store.add_ticket / get_ticket / list_tickets / save_result / set_status /
  reset`. Tickets now survive a Streamlit restart; use `reset()` (or delete data/tickets.sqlite) for a clean demo.
- Streamlit caches module state per process, which is fine: every process opens the same file.

## Step 4 - Smart priority queue and simulator (N5)

**Built**
- sentinel/smart_queue.py: real priority queue behind the unchanged contract (`SmartQueue(agent, concurrency)`,
  `submit`, `stats`, `snapshot`, `set_concurrency`, `shutdown`).
  - On submit: fast triage with `agent.triage_model.predict` -> rank 0 high Incident/Problem, 1 other high,
    2 medium, 3 low; ties run in arrival order. If the fast model fails the ticket still queues (rank 2).
  - Worker threads run the full `agent.triage`, at most `concurrency` at once; statuses queued -> processing ->
    triaged. A failing ticket goes back to "new" and into `snapshot()["failed"]`; the queue keeps going.
  - `set_concurrency(n)` applies to the next ticket picked; `shutdown()` finishes running tickets, waiting ones stay
    "queued".
  - Extras (additive, contract untouched): `submit_many(ids)` (classify a burst first, then queue it at once, so
    urgent tickets are not overtaken by the first arrivals), `on_result(ticket_id, result)` callback,
    `fast_triage[ticket_id]` = {type, priority, rank}, `wait_idle(timeout)`, `QueueStats.failed`.
- sentinel/simulator.py (new): `DEMO_TICKETS` (10: 3 VPN outage tickets incl. 1 German, a refund/legal-threat trap,
  2 German routine, 4 English routine; routine ones arrive first) and `fire(queue, n=10)` -> ticket ids.
  Ticket wording was checked against the real triage model so the labels come out as intended.
- memory/store.py: `VectorStore` now serializes access to its shared SQLite connection and matrix cache with a lock,
  because the queue's worker threads search it concurrently.

**Files**: sentinel/smart_queue.py, sentinel/simulator.py (new), memory/store.py, tests/test_smart_queue.py (new),
tests/test_simulator.py (new).

**Verified**
- `pytest -q tests/test_smart_queue.py tests/test_simulator.py` -> 14 passed (3 runs): burst runs in urgency order,
  an urgent ticket jumps tickets already waiting, peak concurrency equals the limit (3 of 12), set_concurrency up
  and down, statuses + stats + snapshot, failure handling, on_result, shutdown.
- `pytest -q` -> 100 passed.
- `fire()` on the real `SentinelAgent` (extractive writer, hash index of 22,869 kb tickets, concurrency 2):

  | arrival | ticket | fast triage | rank | finished |
  |---|---|---|---|---|
  | 1 | CSV export of usage reports | Incident / medium | 2 | 5 |
  | 2 | Änderung der Rechnungsadresse | Request / low | 3 | 8 |
  | 3 | Urgent: VPN outage affecting all users | Incident / high | 0 | 2 |
  | 4 | Adding a new team member | Request / medium | 2 | 6 |
  | 5 | VPN connection failure - critical | Incident / high | 0 | 1 |
  | 6 | Dringend: VPN-Ausfall im gesamten Unternehmen | Incident / high | 0 | 3 |
  | 7 | Refund demand for double billing | Problem / high | 0 | 4 |
  | 8 | Copy of March invoice | Request / medium | 2 | 7 |
  | 9 | Frage zum Passwort | Change / low | 3 | 9 |
  | 10 | Training materials for new staff | Request / low | 3 | 10 |

  The three VPN outage tickets finish first, then the refund trap, then routine. (1 and 2 swap because they run
  in parallel at concurrency 2.)

**Open issues / notes**
- With the hash index every demo ticket currently ends up `ESCALATE` / tier `PAGE_ONCALL` (gate is Kaushik's/Je's;
  likely low retrieval similarity with hash embeddings). Worth re-checking once the Gemini index exists.
- OutageTracker raised no alert on the burst with hash precedents: that is Step 5 (tune on this burst).
- `throughput_per_min` is huge with the extractive writer (~5 ms per ticket); it is realistic with Gemini.

**For teammates (Kaushik, queue page)**
- `q = SmartQueue(agent, concurrency=settings.queue_concurrency, on_result=lambda tid, r: tracker.observe(r))`
- "Fire demo burst" button: `simulator.fire(q)`; poll `q.stats()` and `q.snapshot()` to render the lanes;
  `q.fast_triage[tid]` gives the arrival labels to show why a ticket jumped.
- Keep one queue per process (e.g. `st.cache_resource`) and call `q.shutdown()` on exit if you can.

## Step 5 - Outage banner polish and incident grouping (B2 + N10)

**Built**
- sentinel/outage.py, tuned on the simulator burst. `observe(result)` / `check()` / `reset()` and the alert's
  `headline` / `subjects` work as before.
  - Why it missed the burst: with 22,869 indexed tickets the two English VPN reports shared 1 of 5 precedents
    (Jaccard 0.11 < 0.4) and the German one shared none (hash cannot match across languages). Raw text similarity
    (hash 0.39, TF-IDF 0.24) ranked routine pairs higher than the outage pair, so neither was usable.
  - New link: same affected system, from an EN+DE term list (VPN, email, login, network, database, website, payments,
    API, printer, phone, storage). Precedent overlap (Jaccard >= 0.4) still links tickets too; links are transitive.
  - `check()` now reports the largest burst in the window, so the banner stays up while unrelated tickets arrive
    (before, any later incident ticket made it disappear).
  - `observe(result, ticket_id=...)` (optional) -> `alert.ticket_ids`; `alert.system` names the shared system.
- sentinel/incidents.py (new): `group_burst(alert, tickets) -> Incident` (pydantic): `incident_id` ("INC-" + first
  ticket number), `title`, `system`, `ticket_ids`, `subjects`, `shared_precedent` (most retrieved across the burst),
  `language` (majority), `status_updates` {"en", "de"}, `status_update` (majority language), `first_seen`.
  Status text is a template (no LLM). It quotes up to two clean sentences of the shared precedent's resolution
  (no `<placeholders>`, questions, greetings or first person) only if the quote is in the update's language
  (checked on the text: some dataset answers are in the other language); otherwise it names the precedent and team.
  No time promises in the text.

**Files**: sentinel/outage.py, sentinel/incidents.py (new), tests/test_outage.py (new), tests/test_incidents.py (new).

**Verified**
- `pytest -q tests/test_outage.py tests/test_incidents.py` -> 19 passed; `pytest -q` -> 119 passed (3 runs).
- Real agent, `simulator.fire()` at concurrency 2, tracker fed from `on_result`: the alert fires on the 3rd VPN
  ticket ("MAJOR INCIDENT: 3 tickets in the last 0.0 min report VPN failing (TKT-08109)"), links SD-1003, SD-1005,
  SD-1006 (incl. the German one), and is still up after all 10 tickets. No routine ticket joins it.
  `group_burst` -> INC-1003 "VPN outage", shared precedent TKT-08109, English text quotes its resolution, German
  text names it (the answer is English).

**How Kaushik calls it ("Group into one incident" button)**
```python
from sentinel import ticket_store
from sentinel.incidents import group_burst
from sentinel.outage import OutageTracker

tracker = OutageTracker()                                      # one per process (st.cache_resource)
q = SmartQueue(agent, settings.queue_concurrency,
               on_result=lambda tid, r: tracker.observe(r, ticket_id=tid))   # ids make the grouping exact
# console page without the queue: tracker.observe(result, ticket_id=tid) after save_result

alert = tracker.check()
if alert:
    st.error(alert.headline)
    if st.button("Group into one incident"):
        incident = group_burst(alert, ticket_store.list_tickets())
        st.subheader(f"{incident.incident_id}: {incident.title}")
        st.write("Linked tickets:", ", ".join(incident.ticket_ids))
        st.text_area("Status update (EN)", incident.status_updates["en"])
        st.text_area("Statusmeldung (DE)", incident.status_updates["de"])
```
`group_burst` is pure (it changes no ticket). Without ticket ids it falls back to matching subjects.
It raises `ValueError` if none of the given tickets belong to the alert.

**Open issues**
- Still waiting on a working Gemini key for Step 1's smoke index and Step 2's Gemini index + numbers.
- With the hash index every demo ticket is ESCALATE / PAGE_ONCALL (gate owned by Kaushik/Je); re-check with Gemini.

## Step 1 follow-up - Gemini smoke index done; Step 2 rate-limit check

**Step 1 closed**: with a working key, `EMBED_PROVIDER=gemini python -m sentinel.ingest_tickets --reset --limit 50`
indexed 50 tickets (`gemini-gemini-embedding-001`, 768 dims). It took 33 s because the call hit the per-minute
limit and the embedder's backoff waited it out, which is exactly what the retry is for.

**Change**: `GeminiEmbedder` now asks for 768 dimensions (`output_dim=768`, `None` = model default 3072).
gemini-embedding-001 is trained so the 768 prefix keeps nearly all the quality; the full index drops from ~280 MB of
vectors to ~70 MB and search is 4x faster. Test added (15 embedder tests).

**Rate limit (measured, free tier)**: `EmbedContentRequestsPerMinutePerUserPerProjectPerModel-FreeTier` = 100,
and every text in a batch counts as one request (100 texts accepted in 3.6 s, then 429 with retryDelay ~40 s).
Google's published free-tier daily cap is 1,000 requests. So the full index (22,869 tickets) is ~3.8 h at best and
not possible in one day on the free tier. Options: enable billing on the key's project (paid tier; ~2.4M tokens
at $0.15 per 1M tokens is roughly $0.40 for the whole index), or index a subset.
