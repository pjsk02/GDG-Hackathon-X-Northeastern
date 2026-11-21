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
