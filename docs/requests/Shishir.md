# Requests from Shishir

## To Kaushik - sentinel/escalation.py, R2 reason wording (low priority, cosmetic)

**What:** in `pre_draft_gate`, the R2 reason says "... although the top label is 'high'" when the predicted
priority is already `high` and only the type is not `Incident` (R1 needs both). Example: "Our VPN is down since the
firewall update" -> Problem / high -> "R2 possible missed outage: P(high)=0.56 >= 0.50 although the top label is 'high'".

**Why:** the operator reads this reason on the board; it looks like a bug.

**Suggested change:** branch the message, e.g. if `predicted_priority == "high"`:
`f"R2 high priority but type is '{predicted_type}', not Incident: P(high)={p:.2f}"`, else keep the current text.
No contract or behaviour change.
