"""Number-and-promise guard on drafted replies (N4).

Owner: D (Sujitha). STUB: returns [] until implemented. sentinel/pipeline.py already calls it after
citation verification; every finding sends the ticket to review with reason
"R6 unbacked <kind> in draft: '<text>'".

Contract (keep stable):
    check_claims(reply: str, verified: list[VerifiedCitation]) -> list[GuardFinding]

Rule: every number, amount of money, percentage, date/duration ("24 hours", "48 Stunden") and
promise phrase ("we guarantee", "full refund", "wir erstatten") in `reply` must also appear in at
least one verified quote (case- and whitespace-insensitive). Anything else is a GuardFinding.
Ticket ids like TKT-01234 are not claims.
"""

from __future__ import annotations

from shared.contracts import GuardFinding, VerifiedCitation


def check_claims(reply: str, verified: list[VerifiedCitation]) -> list[GuardFinding]:
    return []
