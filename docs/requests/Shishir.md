# Requests from Shishir

## To Kaushik - sentinel/escalation.py, R2 reason wording (low priority, cosmetic)

**What:** in `pre_draft_gate`, the R2 reason says "... although the top label is 'high'" when the predicted
priority is already `high` and only the type is not `Incident` (R1 needs both). Example: "Our VPN is down since the
firewall update" -> Problem / high -> "R2 possible missed outage: P(high)=0.56 >= 0.50 although the top label is 'high'".

**Why:** the operator reads this reason on the board; it looks like a bug.

**Suggested change:** branch the message, e.g. if `predicted_priority == "high"`:
`f"R2 high priority but type is '{predicted_type}', not Incident: P(high)={p:.2f}"`, else keep the current text.
No contract or behaviour change.

## To Je - scripts/check_ownership.py drops the first letter of unstaged modified paths (affects everyone)

**What:** `git()` strips every output line (line 20), then the porcelain loop cuts `line[3:]` (line 25). For an
unstaged modification the status is `" M"` with a leading space, which the strip already removed, so the cut eats
the path's first letter. `sentinel/triage.py` is reported as `entinel/triage.py ... is not assigned to anyone`.
The same happens to every teammate with an uncommitted edit, so the check fails with a misleading message.

**Suggested change:** in `git()`, keep leading whitespace for porcelain output, e.g.
`return [line.rstrip() for line in out.stdout.splitlines() if line.strip()]`, or parse with
`git status --porcelain -z`. No other behaviour change.

## To Je - re-run threshold tuning after my Step 2 model

The triage confidences are now calibrated (temperature: type T=0.89, queue T=0.81, priority T=1.43), so
`make tune` and `make dial` results computed on the old model's probabilities are stale. Retrain with
`make sentinel-train` (about 3.5 min) or take my model, then re-run both. Details are in docs/progress/Shishir.md, Step 2.

**Update (Step 5, after reading eval/tune_thresholds.py on main):** without `--model`, `_load_model` fits
`TriageModel().fit(train_df)` in memory. That model is **uncalibrated**, so the thresholds are tuned on different
probabilities from the ones the pipeline sees. `make tune` and `make dial` do not pass `--model`, so please
run `python -m eval.tune_thresholds --model data/sentinel/triage_model.joblib` and
`python -m eval.safety_dial --model data/sentinel/triage_model.joblib` (or add that flag in the Makefile). Its heads are trained on the train slice only (and only 3
temperatures are fitted on validation), so validation stays held out. Alternatively, call `.calibrate(val_df)`
after the in-memory fit.

## To Je - tests/test_team_contracts.py::test_return_types runs a REAL retrain once corrections exist

**What:** `test_return_types` calls `feedback.retrain_challenger()` twice with the real settings. While
`data/sentinel/corrections.jsonl` is empty or missing it returns in milliseconds. Once agents save corrections
in the UI, the first call retrains for real (about 35 s), can **promote a new model** over
`data/sentinel/triage_model.joblib` (with a backup), and makes the "~1 s" contract test slow. The second call
is cached and instant.

**Suggested change:** isolate it like `test_label_correction_roundtrip` already does, e.g.

```python
def test_return_types(tmp_path, monkeypatch):
    ...
    monkeypatch.setattr(feedback, "get_settings", lambda: Settings(corrections_path=tmp_path / "c.jsonl"))
    assert isinstance(feedback.retrain_challenger(), dict)
```

No contract change: with no corrections it returns `{"status": "kept_champion", ...}` without training.

## To Kaushik - ui/pages/agent.py "Correct labels" form: offer the known labels, not free text

**What:** `retrain_challenger()` only learns from corrections whose label is a known class for that head. It
matches case-insensitively, so "High" works, but a typo like "Hardware" is skipped and reported in
`skipped_reasons`. A free `st.text_input` will lose corrections.

**Suggested change:** `st.selectbox(f"Corrected {head}", triage.get_model().classes[head], index=...)`, where
`classes` is `{"type": [...], "queue": [...], "priority": [...]}` on the TriageModel. Also skip saving when the
choice equals the prediction (the retrain ignores those anyway).
