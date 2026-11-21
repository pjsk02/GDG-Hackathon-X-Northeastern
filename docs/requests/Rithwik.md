# Requests from Rithwik

## 2026-11-21 12:15 -> Je: check_ownership.py drops the first letter of unstaged modified files
File: scripts/check_ownership.py
Why: `git()` strips every output line, so the porcelain line ` M memory/embedder.py` becomes `M memory/embedder.py`
and `line[3:]` gives `emory/embedder.py`, which fails the check. Staged and committed files are read correctly,
so it only bites before `git add`, but every teammate will hit it.
Change: in `changed_files()`, do not strip the `git status --porcelain` lines before slicing, e.g.
`out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout` and then
`files.add(line[3:].split(" -> ")[-1].strip('"'))` for each non-empty line.
Until then: `git add` my files before running the check.
Status: open

## 2026-11-21 -> Kaushik: pass ticket ids to OutageTracker.observe (exact incident grouping)
File: ui/pages/queue.py (`_sync_observed_done`), ui/pages/agent.py (preset + custom ticket), api/main.py (`triage_ticket`)
Why: every call is `tracker.observe(result)` without the ticket id, so `alert.ticket_ids` is empty and
`group_burst(alert, tickets)` has to match tickets by subject. That works (it now takes the newest ticket
per subject, so a second demo burst no longer pulls in the first one), but ids make it exact. Je's Step 6 log lists
this too ("outage tracker gets no ticket ids").
Change: one keyword argument per call, the id is already in scope:
- ui/pages/queue.py: `tracker.observe(rec.result, ticket_id=tid)`
- ui/pages/agent.py (2x): `tracker.observe(res, ticket_id=tid)`
- api/main.py: `_OUTAGE_TRACKER.observe(result, ticket_id=ticket_id)`
`observe(result, now=None, ticket_id=None)` has accepted this since PR #1, so the change is safe on its own.
Until then: subject matching (newest ticket per subject) in sentinel/incidents.py.
Status: open

## 2026-11-21 -> Kaushik: show end-to-end latency and detected language in the console (brief requirement)
File: ui/pages/agent.py (triage section, "4. Three triage questions"), api/static/sentineldesk.html (ticket detail)
Why: the brief's Live Triage Console must show "type, queue, priority, confidence score, and end-to-end latency".
The pipeline already fills `SentinelResult.latency_ms` and `stage_latency_ms` (triage / retrieval / generation ms) and
both are saved in ticket_store, but no SentinelDesk page displays them; the only latency on screen is in the old Q&A
scaffold (ui/app.py). The agent page also does not show the detected language, which is how judges see that language
is detected from raw text rather than read from the dataset.
Change: two more badges next to Type / Team / Priority in ui/pages/agent.py, e.g.

```python
                badge("Language", f"{res.detected_language.upper()} ({res.language_confidence:.0%})"),
                badge("Latency", f"{res.latency_ms / 1000:.2f} s"),
```
and optionally a caption with the stages:
`st.caption(" · ".join(f"{k.removesuffix('_ms')} {v:.0f} ms" for k, v in res.stage_latency_ms.items()))`.
In /desk, next to "Lang: ...", add `Latency: ${((r.latency_ms || 0) / 1000).toFixed(2)} s`.
Results saved before this change still load: `latency_ms` defaults to 0.0 and `stage_latency_ms` to {}.
Until then: latency is only visible in data/eval/latest/report.json (p50 1.34 s / p95 6.59 s) and the API response.
Status: open
