# Rithwik - Role C: retrieval, ticket store, smart queue, outage and incidents

Branch: `Rithwik-Branch` · Your files: see `Rithwik-Branch` in docs/team/ownership.json · Progress log: docs/progress/Rithwik.md

## Kickoff prompt (paste into your agent after the starter prompt)

```text
You are Rithwik's coding agent for the SentinelDesk hackathon repo (https://github.com/pjsk02/GDG-Hackathon-X-Northeastern). I am Rithwik, role C (Gemini embeddings and the search index, cross-lingual check, ticket store, smart priority queue, outage detection and incident grouping).

1. Make sure you are inside the repo on branch Rithwik-Branch with the latest main merged. If not, do the starter checks in docs/prompts/00-starter.md first.
2. Fetch my plan from GitHub: https://raw.githubusercontent.com/pjsk02/GDG-Hackathon-X-Northeastern/main/docs/prompts/Rithwik.md (the same file is at docs/prompts/Rithwik.md). Also read CLAUDE.md, docs/team/README.md and docs/PRD.md.
3. Follow the plan one step at a time, in order. Inside a step, work autonomously: split independent pieces across subagents (builder for code in my files, Explore for reading other people's code, test-runner for checks, ownership-reviewer before pushing) and run them in parallel when they touch different files. Only ask me when you are truly blocked.
4. Edit only my files (docs/team/ownership.json, Rithwik-Branch). Push only to Rithwik-Branch. Never push to main.
5. When a step's "Done when" list is met, run /ship-step <N>, give me the report, and stop. Start the next step only after I reply "yes, you can proceed".

Start with Step 1 now.
```

## What you own and who depends on you

- memory/embedder.py, memory/store.py, sentinel/ingest_tickets.py, sentinel/ticket_store.py,
  sentinel/smart_queue.py, sentinel/simulator.py (new), sentinel/outage.py, sentinel/incidents.py (new),
  eval/crosslingual_check.py (new).
- Kaushik builds every UI page on `ticket_store` and the queue page on `SmartQueue` + your simulator. Both exist on
  main as working stubs with the final interface, so he is not blocked; keep the interface exactly.
- The demo uses the index you build with Gemini embeddings.

## Step 1 - Gemini embedder (F4)

- Add `GeminiEmbedder` to memory/embedder.py and return it from `get_embedder` when `EMBED_PROVIDER=gemini`.
  Use the google-genai SDK already installed (check its current embed API in the installed version),
  `settings.gemini_embed_model`, batches of `settings.gemini_embed_batch`, retrieval task types for documents vs
  queries (`is_query`), unit-normalised float32 output, and retry with backoff on HTTP 429/5xx.
- Name it like the others (`self.name = f"gemini-{model}"`) so vectors stay tagged per embedder.
- Tests in `tests/test_embedder*.py` with a mocked client (no network in tests).

Done when: tests pass and a 50-ticket smoke index works with your key (`python -m sentinel.ingest_tickets --reset --limit 50` with `EMBED_PROVIDER=gemini`).

## Step 2 - Demo index and cross-lingual check (B1)

- Check the embedding rate limit first, then build the full index: `EMBED_PROVIDER=gemini make sentinel-index`.
  Log time taken and any throttling.
- Build `eval/crosslingual_check.py`: for German VALIDATION tickets, the share of top-5 precedents that are English,
  and how often the top precedent has the same queue. Compare `hash` vs `gemini`. Skip the ticket itself in results.
- Put a download link for the built `data/sentinel.sqlite` (Google Drive or similar, shared with the team only) in
  docs/progress/Rithwik.md so the demo laptop does not re-embed.

Done when: the numbers are in your log and the index file is shared.

## Step 3 - Ticket store on SQLite

Replace the in-memory internals of sentinel/ticket_store.py with SQLite at `settings.ticket_store_path`, keeping
every function name, argument and return type. Thread-safe (the queue writes from worker threads), `reset()` clears
the table, results stored as JSON (`SentinelResult.model_dump_json()`).

Done when: `tests/test_ticket_store*.py` covers add, list by status, save_result, set_status, persistence across
two store instances, and concurrent writes; `pytest -q` passes.

## Step 4 - Smart priority queue and simulator (N5)

- sentinel/smart_queue.py: on `submit`, classify immediately with the fast triage model
  (`agent.triage_model.predict`) and give high-priority Incidents a higher priority; worker threads run the full
  `agent.triage` with at most `concurrency` at once; update ticket statuses (queued -> processing -> triaged);
  `stats()` and `snapshot()` give live numbers; `set_concurrency` takes effect for the next ticket; `shutdown()`
  stops workers cleanly.
- sentinel/simulator.py: `DEMO_TICKETS` (10 tickets: 3 VPN outage tickets that form a burst, a refund trap, German
  tickets, routine ones) and `fire(queue, n=10)` that adds them to the store and submits them.
- Tests with a fake agent (sleep a few ms) proving urgent tickets jump ahead and the limit is respected.

Done when: tests pass and `fire()` on the real agent shows urgent tickets finishing first (log the order).

## Step 5 - Outage banner polish and incident grouping (B2 + N10 stretch)

- Keep `OutageTracker.observe(result)` working; tune it on the simulator's burst.
- sentinel/incidents.py: `group_burst(alert, tickets) -> Incident` (pydantic model in that file) with incident id,
  linked ticket ids, the shared precedent, and one status-update text built from the shared precedent's resolution
  (template, no LLM, English and German).
- Tests for grouping and the status text.

Done when: tests pass; write in your log how Kaushik calls it from the "Group into one incident" button. Open a PR into main and tell Je.
