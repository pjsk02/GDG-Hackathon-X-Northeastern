# SentinelDesk team plan

Five people, five branches, no shared files, so merges never conflict. Each person's agent works through a numbered
plan one step at a time and waits for "yes, you can proceed" between steps.

## Who does what

| Person | Branch | Role | Plan |
|---|---|---|---|
| Je | `Je-Branch` | A - data, evaluation, thresholds, safety dial, README, demo. Integration lead: merges PRs | [docs/prompts/Je.md](../prompts/Je.md) |
| Shishir | `Shishir-Branch` | B - triage model: calibration, why-this-label, learning loop | [docs/prompts/Shishir.md](../prompts/Shishir.md) |
| Rithwik | `Rithwik-Branch` | C - Gemini embeddings and index, cross-lingual check, ticket store, smart queue, incidents | [docs/prompts/Rithwik.md](../prompts/Rithwik.md) |
| Sujitha | `Sujitha-Branch` | D - Gemini writer, number-and-promise guard, injection rule, PII view | [docs/prompts/Sujitha.md](../prompts/Sujitha.md) |
| Kaushik | `Kaushik-Branch` | E - three-tier gate, Streamlit pages (board + side panel), API, pipeline wiring | [docs/prompts/Kaushik.md](../prompts/Kaushik.md) |

The exact file list per person is [ownership.json](ownership.json). The edit guard hook (`.claude/hooks/ownership_guard.py`)
blocks an agent from editing anything outside its person's list, and `make check-ownership` checks a branch before push.

## How a day goes

1. **Starter prompt** ([docs/prompts/00-starter.md](../prompts/00-starter.md)): clone or update, switch to your branch,
   install, run tests. Paste it once into your agent.
2. **Kickoff prompt** (top of your plan file): the agent fetches your plan from GitHub and starts Step 1.
3. **Each step:** the agent builds autonomously with subagents, then runs `/ship-step <N>`: tests, ownership check,
   progress log in `docs/progress/<YourName>.md`, commit, push to your branch. It then stops and asks.
4. **You reply** `yes, you can proceed` and it starts the next step (`/next-step` does the same in a fresh session).
5. **Pull requests:** after a step that others depend on, open a PR from your branch into `main` on GitHub
   (Compare & pull request). Je merges. Because nobody shares files, every PR merges cleanly.
6. **Staying current:** every step starts with `/sync-main`, which merges the latest main into your branch.

Commands for the agent: `/next-step`, `/ship-step <N>`, `/sync-main`, and the built-in
`/goal <condition>` to keep it working until a step is truly done, for example:
`/goal Step 3 in docs/prompts/Kaushik.md is shipped: Done-when checks pass, pytest passes, pushed to Kaushik-Branch, or stop after 40 turns`.

## Why there are no merge conflicts

- Every file has exactly one owner. Shared files (shared/, pyproject.toml, requirements.txt, Makefile, CLAUDE.md,
  .claude/, docs/team/, docs/prompts/) were prepared once on main and are frozen.
- Every cross-team function already exists on main as a stub with its final signature, and the pipeline already
  calls it. You fill in your own file; nobody waits and nobody edits someone else's file to wire things up.
- Branches take main by merging (`make sync`), never by rebasing, so nobody force-pushes.
- tests/test_team_contracts.py fails if someone changes a contract.

## Contracts (frozen signatures, already on main)

| Function | File | Owner | Used by |
|---|---|---|---|
| `explain(model, text, top_n=3) -> dict[str, list[str]]` | sentinel/explain.py | Shishir | pipeline -> `result.explanations` |
| `record_correction(c)`, `list_corrections()`, `retrain_challenger() -> dict` | sentinel/feedback.py | Shishir | manager page, agent panel |
| `TriageModel.predict(subject, body)`, `get_model()` | sentinel/triage.py | Shishir | pipeline, queue |
| `get_embedder(settings)` incl. `EMBED_PROVIDER=gemini` | memory/embedder.py | Rithwik | store, ingest |
| `add_ticket`, `get_ticket`, `list_tickets`, `save_result`, `set_status`, `reset` | sentinel/ticket_store.py | Rithwik | all UI pages |
| `SmartQueue(agent, concurrency)`: `submit`, `stats`, `snapshot`, `set_concurrency`, `shutdown` | sentinel/smart_queue.py | Rithwik | queue page |
| `OutageTracker.observe(result)` | sentinel/outage.py | Rithwik | agent board, queue page |
| `SYSTEM_PROMPT`, `build_user_prompt`, `extractive_draft`, `verify_citations` | sentinel/writer.py | Sujitha | pipeline |
| `check_claims(reply, verified) -> list[GuardFinding]` | sentinel/claims.py | Sujitha | pipeline -> `result.guard_findings` |
| `detect_injection(text) -> list[str]` | sentinel/injection.py | Sujitha | pipeline -> rule R7 |
| `mask_pii(text) -> (masked, counts)` | sentinel/pii.py | Sujitha | pipeline, agent panel |
| `pre_draft_gate`, `post_draft_gate`, `decide_tier(decision, reasons)` | sentinel/escalation.py | Kaushik | pipeline |
| `SentinelAgent.triage(subject, body, ...) -> SentinelResult` | sentinel/pipeline.py | Kaushik | everyone |
| `load_train_val_test()`, `split_train_val()` | sentinel/dataset.py | Je | Shishir, Je |
| `thresholds.load(settings)` | sentinel/thresholds.py | Je | pipeline |
| Types: `SentinelResult` (tier, briefing, explanations, injection_flags, guard_findings, pii_masked_body), `GuardFinding`, `LabelCorrection`, `SentinelDraft.briefing` | shared/contracts.py | frozen | everyone |

Data files that pass between people (all under gitignored `data/`):

| File | Written by | Read by |
|---|---|---|
| data/sentinel/kb_train.csv, holdout_test.csv | Je (`make sentinel-split`) | everyone |
| data/sentinel/triage_model.joblib | Shishir | pipeline |
| data/sentinel.sqlite (index) | Rithwik (demo build with Gemini) | pipeline |
| data/sentinel/thresholds.json | Je (`make tune`) | pipeline |
| data/eval/safety_dial.json | Je (`make dial`) | manager page |
| data/eval/latest/report.json | Je (`make sentinel-eval`) | manager page, README |
| data/eval/calibration.json | Shishir | manager page, README |
| data/sentinel/corrections.jsonl | agent panel via feedback.py | Shishir's retrain |

## Changing something you do not own

Write the request in `docs/requests/<YourName>.md` (you own that file): what, why, and the exact change. Push it and
tell the owner (or Je for shared files). The owner makes the change on their branch, or Je changes a shared file on
main; then everyone runs `make sync`. Meanwhile, code against the documented interface.

Changing a contract: agree it with the owner and Je first. Je updates the stub, contracts.py and the contract test
on main in one commit.

## Checkpoints

1. **+0:45** Everyone has run the starter prompt and Step 1. Je has the split, baseline metrics and thresholds started.
2. **+2:00** Gemini path works (Sujitha), three-tier gate and board shell (Kaushik), Gemini embedder (Rithwik),
   calibration (Shishir), thresholds tuned (Je). PRs merged.
3. **+3:15** Guards, explanations, ticket store, queue, customer and manager pages merged. Eval re-run.
4. **Deadline - 1:00** Feature freeze: only bug fixes and two timed demo rehearsals.

## One-time setup Je does on GitHub

- Settings -> Branches -> add a rule for `main`: require a pull request before merging. Agents also have a deny
  rule for pushing to main, but the GitHub rule is the real lock.
- Add Kaushik, Sujitha, Rithwik and Shishir as collaborators (Settings -> Collaborators) if not done.

## Permissions and autonomy

`.claude/settings.json` (shared) sets `acceptEdits`, allows the usual git/make/uv/python/pytest commands and pushes
to `*-Branch`, and denies pushing to main, force-pushing and rebasing. Trust the folder when Claude Code asks, or
the allow rules do not apply. For even fewer prompts, start Claude with `claude --permission-mode auto`
(auto mode cannot be set in a project file). Personal tweaks go in `.claude/settings.local.json` (gitignored).
