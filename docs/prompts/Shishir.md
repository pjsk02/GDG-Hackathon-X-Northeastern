# Shishir - Role B: triage model (calibration, why-this-label, learning loop)

Branch: `Shishir-Branch` · Your files: see `Shishir-Branch` in docs/team/ownership.json · Progress log: docs/progress/Shishir.md

## Kickoff prompt (paste into your agent after the starter prompt)

```text
You are Shishir's coding agent for the SentinelDesk hackathon repo (https://github.com/pjsk02/GDG-Hackathon-X-Northeastern). I am Shishir, role B (triage model: calibration, why-this-label explanations, learning loop). I wrote the original pipeline.

1. Make sure you are inside the repo on branch Shishir-Branch with the latest main merged. If not, do the starter checks in docs/prompts/00-starter.md first.
2. Fetch my plan from GitHub: https://raw.githubusercontent.com/pjsk02/GDG-Hackathon-X-Northeastern/main/docs/prompts/Shishir.md (the same file is at docs/prompts/Shishir.md). Also read CLAUDE.md, docs/team/README.md and docs/PRD.md.
3. Follow the plan one step at a time, in order. Inside a step, work autonomously: split independent pieces across subagents (builder for code in my files, Explore for reading other people's code, test-runner for checks, ownership-reviewer before pushing) and run them in parallel when they touch different files. Only ask me when you are truly blocked.
4. Edit only my files (docs/team/ownership.json, Shishir-Branch). Push only to Shishir-Branch. Never push to main.
5. When a step's "Done when" list is met, run /ship-step <N>, give me the report, and stop. Start the next step only after I reply "yes, you can proceed".

Start with Step 1 now.
```

## What you own and who depends on you

- sentinel/triage.py, sentinel/explain.py, sentinel/feedback.py, sentinel/calibration.py (new).
- The pipeline already calls `explain.explain(model, text)` and fills `result.explanations`; Kaushik shows it.
- Kaushik's agent panel calls `feedback.record_correction(...)`; the manager page calls `feedback.retrain_challenger()`.
- Je's eval reads `sentinel/calibration.py` if it exists.

What changed on main since your last commit (read it once): the prompt, fallback draft and citation checks moved
from sentinel/pipeline.py to sentinel/writer.py (owner Sujitha); `extractive_draft` was fixed (it was missing the
required `refused` field, so every fallback draft raised a ValidationError); new stubs and contract fields were added
(see docs/team/README.md, "Contracts"); `dataset.load_train_val_test()` gives a validation slice.

## Step 1 - Setup and base check

- Get the data and build locally (see CLAUDE.md "Setup"): split, train, index. Use your Ollama setup if you like.
- Run `python -m sentinel.pipeline "Our VPN is down since the firewall update"` with `LLM_PROVIDER=extractive`
  and with `ollama`; confirm a grounded draft, `result.tier` set and nothing broken by the writer.py move.
- `pytest -q` passes.

Done when: both runs work and you logged anything odd in docs/progress/Shishir.md.

## Step 2 - Train on the train slice and calibrate (F2)

- In `sentinel/triage.py`: `--train` fits on the TRAIN slice from `dataset.load_train_val_test()` and calibrates
  each head on the VALIDATION slice (scikit-learn's current API: `CalibratedClassifierCV` with a frozen/prefit
  estimator, method "sigmoid" or "isotonic"; pick by validation log-loss). Keep `predict()` fast (a few ms).
- Create `sentinel/calibration.py`: `report(model, df) -> dict` with expected calibration error per head and
  10-bin reliability data; `main()` writes `data/eval/calibration.json` and `data/eval/calibration.png`.
- Save the model with metadata (`trained_on`, `calibrated`, `classes`). The holdout evaluation still prints metrics.

Done when: ECE before and after calibration is logged, the model is saved, holdout Macro-F1 did not drop by more
than 0.01, tests pass (`tests/test_calibration*.py`, offline, tiny synthetic data).

## Step 3 - Why-this-label (N3)

Implement `explain(model, text, top_n=3)` in sentinel/explain.py (contract in the file):
- For each head, take the predicted class and rank WORD n-gram features by coefficient x tf-idf value
  (skip the character n-grams). Reach the linear coefficients through the calibration wrapper.
- Return up to `top_n` readable phrases per head, e.g. `{"type": ["bricht ständig ab"], "priority": ["alle Mitarbeitenden"]}`.
- Under 5 ms per ticket; never raise on empty or very short text.

Done when: tests pass (`tests/test_explain*.py`), and 5 real tickets give sensible words (paste them in the log).

## Step 4 - Learning loop (N8)

Implement `retrain_challenger()` in sentinel/feedback.py (contract in the file):
- Train a challenger on the train slice plus all recorded corrections, score champion and challenger on the
  VALIDATION slice (type and priority Macro-F1, high-priority-incident recall).
- Promote only if neither metric drops; keep a backup of the old model; reset the cached model
  (`triage._CACHED = None`) so the app picks up the new one.
- Return the documented dict. Never read the holdout here.

Done when: tests with synthetic corrections pass, and a real run returns "promoted" or "kept_champion" with numbers.

## Step 5 - Hardening and handoff

- Edge cases: empty subject, 5,000-character body, German-only, emoji. Latency check (p95 per ticket).
- Write in docs/progress/Shishir.md exactly how Kaushik should call `record_correction` and show
  `retrain_challenger()` results.
- Optional, only if everything else is shipped: a Keras-on-embeddings comparison row for the README.

Done when: edge-case tests pass and the handoff notes are pushed. Open a PR into main and tell Je.
