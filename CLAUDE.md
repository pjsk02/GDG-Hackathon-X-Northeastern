# SentinelDesk: team rules for every agent

SentinelDesk triages support tickets (type, team, priority + confidence), applies a safety gate, retrieves past
resolved tickets and drafts a reply that cites them. Built for the GDG Hackathon x Northeastern (6 hours).
Product spec: docs/PRD.md. Team plan: docs/team/README.md. Your personal plan: docs/prompts/<YourName>.md.

## Who you are working for

Five people, five branches. Find your person from the branch name:

| Branch | Person | Role |
|---|---|---|
| Je-Branch | Je | A - data, evaluation, README, demo, integration lead |
| Shishir-Branch | Shishir | B - triage model: calibration, explanations, learning loop |
| Rithwik-Branch | Rithwik | C - retrieval, ticket store, smart queue, outage/incidents |
| Sujitha-Branch | Sujitha | D - Gemini writer and guardrails |
| Kaushik-Branch | Kaushik | E - UI pages, three-tier gate, pipeline wiring, API |

## Hard rules (a hook enforces the first two)

1. Edit only files your person owns (docs/team/ownership.json). The ownership guard blocks the rest.
   Need a change elsewhere? Write it in docs/requests/<YourName>.md, tell your user, and code against the
   documented interface meanwhile. Shared files (shared/, pyproject.toml, Makefile, CLAUDE.md, .claude/,
   docs/team/, docs/prompts/) change only on main, by Je.
2. Never edit on main. Work on <YourName>-Branch. Push only there: `git push -u origin <YourName>-Branch`.
   Never push to main, never force-push, never rebase a pushed branch. To get main: `make sync` (a merge).
3. Keep contracts stable: the function names, arguments and return types written at the top of each module in
   sentinel/ and in shared/contracts.py. tests/test_team_contracts.py checks them. Changing one needs the owner and Je.
4. Never read the holdout's labels or answers except inside evaluation code that scores predictions.
   Tune and calibrate on the validation slice (sentinel.dataset.load_train_val_test). Never index the holdout.
5. No secrets in git. API keys live in .env (gitignored). Never commit data/ or .env.

## How to work: one step at a time, with a gate

Your plan has numbered steps. For each step:
- Build it autonomously. Split independent pieces across subagents (`builder` for code in your files,
  `Explore` for reading others' code, `test-runner` for checks, `ownership-reviewer` before pushing).
  Run several subagents at once when they touch different files.
- Ask your user only when truly blocked: a missing API key or dataset, a change in someone else's file,
  anything destructive or irreversible.
- Finish with the `ship-step` skill: tests, ownership check, progress log, commit, push to your branch.
- Then STOP and ask: "Reply **yes, you can proceed** to start Step N+1." Do not begin the next step until your
  user replies with that approval.

Useful commands: `/next-step` (start your next step), `/ship-step <N>`, `/sync-main`,
`/goal <condition>` (built in: keep working until the condition holds, e.g.
`/goal Step 2 in docs/prompts/Rithwik.md is shipped: its Done-when checks pass, pytest passes, pushed to Rithwik-Branch, or stop after 40 turns`).

## Setup and commands

```bash
uv venv --python 3.12 && uv pip install -e ".[all]"   # once
cp .env.example .env                                  # then add GEMINI_API_KEY if your role needs it
mkdir -p data/raw && curl -L -o data/raw/aa_dataset-tickets-multi-lang-5-2-50-version.csv \
  https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets/resolve/main/aa_dataset-tickets-multi-lang-5-2-50-version.csv
make sentinel-split      # 80/20 split + leakage report -> data/sentinel/
make sentinel-train      # triage model -> data/sentinel/triage_model.joblib
make sentinel-index      # knowledge-base index (EMBED_PROVIDER=hash for dev; fast and offline)
make console             # Streamlit console
pytest -q                # all tests, offline, seconds
make team-test           # contract tests only
make check-ownership     # does this branch touch only my files?
make sync                # merge latest main into my branch
```

On Windows use `.venv\Scripts\activate`; elsewhere `source .venv/bin/activate`, or prefix commands with `uv run`.

## Code map

- sentinel/pipeline.py (E): `SentinelAgent.triage(subject, body)` -> `SentinelResult`. Orchestrates everything.
- sentinel/triage.py, explain.py, feedback.py (B) - classifier, why-this-label, learning loop.
- memory/embedder.py, memory/store.py, sentinel/ingest_tickets.py, ticket_store.py, smart_queue.py, outage.py (C).
- sentinel/writer.py, claims.py, injection.py, pii.py, agent/llm_router.py (D) - prompt, guards, Gemini.
- sentinel/escalation.py, ui/, api/ (E) - gate and tiers, Streamlit pages, FastAPI.
- sentinel/dataset.py, thresholds.py, eval/ (A) - split, validation slice, thresholds, metrics.
- shared/contracts.py, shared/settings.py - frozen shared types and config.

Style: Python 3.12, type hints, small functions, docstring at the top of each module stating its contract and owner.
Every new behaviour gets a test in tests/test_<module>*.py that runs offline.
