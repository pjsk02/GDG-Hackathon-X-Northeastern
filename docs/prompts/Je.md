# Je - Role A: data, evaluation, thresholds, safety dial, README, demo (integration lead)

Branch: `Je-Branch` · Your files: see `Je-Branch` in docs/team/ownership.json · Progress log: docs/progress/Je.md

## Kickoff prompt (paste into your agent after the starter prompt)

```text
You are Je's coding agent for the SentinelDesk hackathon repo (https://github.com/pjsk02/GDG-Hackathon-X-Northeastern). I am Je, role A (data, evaluation, thresholds, safety dial, README, demo) and the integration lead.

1. Make sure you are inside the repo on branch Je-Branch with the latest main merged. If not, do the starter checks in docs/prompts/00-starter.md first.
2. Fetch my plan from GitHub: https://raw.githubusercontent.com/pjsk02/GDG-Hackathon-X-Northeastern/main/docs/prompts/Je.md (the same file is at docs/prompts/Je.md). Also read CLAUDE.md, docs/team/README.md and docs/PRD.md.
3. Follow the plan one step at a time, in order. Inside a step, work autonomously: split independent pieces across subagents (builder for code in my files, Explore for reading other people's code, test-runner for checks, ownership-reviewer before pushing) and run them in parallel when they touch different files. Only ask me when you are truly blocked.
4. Edit only my files (docs/team/ownership.json, Je-Branch). Push only to Je-Branch. Never push to main.
5. When a step's "Done when" list is met, run /ship-step <N>, give me the report, and stop. Start the next step only after I reply "yes, you can proceed".

Start with Step 1 now.
```

## What you own and who depends on you

- Data split and validation slice (sentinel/dataset.py), gate thresholds (sentinel/thresholds.py), all of eval/
  except `eval/crosslingual_check.py` (Rithwik) and `eval/cases_guardrails.jsonl` (Sujitha), README, demo docs.
- Kaushik's manager page reads your `data/eval/safety_dial.json` and `data/eval/latest/report.json`.
- The pipeline already calls `thresholds.load(settings)`; your tuned values take effect as soon as
  `data/sentinel/thresholds.json` exists.

## Step 1 - Data and baseline numbers

- Download the dataset (26 MB): `mkdir -p data/raw && curl -L -o data/raw/aa_dataset-tickets-multi-lang-5-2-50-version.csv https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets/resolve/main/aa_dataset-tickets-multi-lang-5-2-50-version.csv`
- `make sentinel-split` and check the leakage report says `ok: True` with 0 id overlap. Note the identical-body
  overlap count; if it is above 0, list a few examples in your progress log (judges may ask).
- `make sentinel-train`, then `make sentinel-index` with `EMBED_PROVIDER=hash` (fast, offline).
- `python -m eval.sentinel_eval --triage-only` to get baseline Macro-F1 and high-priority incident recall.
- Check `sentinel.dataset.load_train_val_test()` sizes (train 90% / val 10% of kb, holdout 20%).
- Write a short "How to get the data" note for teammates in docs/progress/Je.md (they will copy the commands).

Done when: baseline metrics and split sizes are in docs/progress/Je.md, `pytest -q` passes.

## Step 2 - Tune thresholds on the validation slice (F1, leakage fix)

Build `eval/tune_thresholds.py` (`make tune`):
- Train a triage model on the TRAIN slice only (`TriageModel().fit(train)` in memory; once Shishir's
  train-only model exists, load it instead). Predict the VALIDATION slice.
- Retrieval similarity for a validation ticket must skip itself: the index holds all of kb_train, so search k+1 and
  drop the hit with the same ticket_id.
- Sweep `triage_confidence_min`, `high_priority_alert_probability`, `retrieval_similarity_min` on a small grid.
  Objective: high-priority-incident recall at least 0.90 on validation with the lowest on-call rate
  (use `escalation.decide_tier`; until Kaushik merges, the placeholder treats every escalation as on-call).
- Write `data/sentinel/thresholds.json` (the three keys plus the validation metrics you got) and print a table.
- Add `tests/test_thresholds_tuning.py` (tiny synthetic data, runs offline).

Done when: thresholds.json exists, `thresholds.load()` returns your values, the holdout was not read, tests pass.

## Step 3 - Safety dial data and chart (N2)

Build `eval/safety_dial.py` (`make dial`) on the validation slice:
- For a sweep of thresholds, compute escalation rate, on-call rate, agent-review rate, auto-draft rate and
  high-priority-incident recall.
- Write `data/eval/safety_dial.json` exactly in this shape (Kaushik reads it):
  `{"generated_at": "...", "split": "validation", "points": [{"triage_confidence_min": 0.55, "high_priority_alert_probability": 0.5, "retrieval_similarity_min": 0.55, "oncall_rate": 0.31, "review_rate": 0.22, "auto_rate": 0.47, "hpi_recall": 0.91}], "chosen": {...same keys...}}`
  (the numbers above only show the format).
- Also save `data/eval/safety_dial.png` (recall against workload).

Done when: the JSON and PNG exist, the format matches, tests pass. Tell Kaushik the file is ready.

## Step 4 - Evaluation upgrades

Extend `eval/sentinel_eval.py`:
- Report tier rates (auto-draft, agent review, on-call), guard findings per ticket, injection hits, and Shishir's
  calibration numbers if `sentinel/calibration.py` exists (skip cleanly if not).
- Load behaviour cases from both `eval/sentinel_cases.jsonl` and `eval/cases_guardrails.jsonl` (Sujitha's, if present).
- Add 5 cases to `eval/sentinel_cases.jsonl`: a German ticket that should match an English fix, a reply-number trap,
  an injection in German, an empty-subject outage, a routine password reset.
- Always also write `data/eval/latest/report.json` (stable path for the manager page).

Done when: `python -m eval.sentinel_eval --sample 20 --compare extractive` runs end to end and writes the report.

## Step 5 - README and cleanup (F6)

- Move the old scaffold README to `docs/scaffold.md`; write a new README.md for judges: what SentinelDesk does,
  the architecture (a mermaid diagram), how to run it (setup, data, `make` targets), the leakage statement
  (split recipe, validation-only tuning, index holds kb only), the metrics table (placeholders until Step 6),
  bonus features, team.
- Delete AUDIT.md. Remove `samples/` only if `pytest -q` still passes without it.
- Write `docs/demo/demo_tickets.md` (8-10 tickets for the live demo: EN/DE outage, refund trap, injection,
  empty subject, PII, routine) and `docs/demo/script.md` (the 5-minute script from the PRD, with timings).

Done when: README renders on GitHub, tests pass, demo files exist.

## Step 6 - Integration and final numbers (lead)

- Review and merge teammates' PRs into main on GitHub (they never conflict; check the PR only touches the
  author's files). After merging, tell everyone to run `/sync-main`.
- On merged main: rebuild the index with the demo embedder, run `make tune`, `make dial`, then
  `python -m eval.sentinel_eval --sample 120 --compare gemini extractive`.
- Fill the README metrics table from `data/eval/latest/report.json` only. Never quote numbers tuned on the holdout.
- Run the demo script twice with a timer and log issues for the owners.

Done when: README has real numbers, the demo runs start to finish on the demo laptop.

## Lead duties (any time)

- Shared files (shared/, pyproject.toml, Makefile, CLAUDE.md, .claude/, docs/team/, docs/prompts/) change only on
  main, by you. To edit them, set `SENTINEL_ALLOW_MAIN=1` in the terminal where you start Claude Code, switch to
  main, make the change, run `pytest -q`, push main from your own terminal, and tell everyone to `make sync`.
- Watch docs/requests/*.md on teammates' branches for requests addressed to you.
