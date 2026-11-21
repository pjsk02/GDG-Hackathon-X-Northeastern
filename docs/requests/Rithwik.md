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
