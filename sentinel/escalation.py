"""The escalation & safety gate: deterministic rules, each with a reason an operator can read.

Nothing here is a model judgement call. Every rule is a threshold or a pattern, so the same
ticket always gets the same decision and the console can print *why*.

Pre-draft rules (checked before the LLM is called):
    R1  predicted high priority AND Incident            -> major incident, page a human
    R2  P(high) over the alert threshold                -> possible missed outage (recall safety net)
    R3  triage confidence below threshold               -> the classifier is guessing
    R4  best precedent similarity below threshold       -> no historical precedent to ground on
    R5  the ticket demands a commitment (refund, SLA
        credit, legal guarantee, cancellation...)       -> commercial/legal, never auto-answered
Post-draft rule:
    R6  no citation survived verbatim verification      -> the draft is ungrounded
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.contracts import EscalationDecision, Tier

# --- thresholds (overridable via Settings, and live in the console sidebar) ------
# Tuned on 1,200 holdout tickets. At these values the gate escalates ~61% of tickets and catches
# 89% of the true high-priority Incidents and 67% of every mistriaged ticket. Loosening to
# 0.50/0.50 escalates 50% but catches only 83% of them: the dial is a business decision, so the
# console exposes it instead of hiding it.
TRIAGE_CONFIDENCE_MIN = 0.55
RETRIEVAL_SIMILARITY_MIN = 0.55
HIGH_PRIORITY_ALERT_PROBABILITY = 0.50

# --- R5: requests no historical resolution can authorise -------------------
# English + German. Matched on the raw ticket text, word-boundary anchored.
COMMITMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("refund or compensation demanded", re.compile(
        r"\b(full refund|refund (me|us|my|the)|money back|reimburse\w*|compensat\w+|"
        r"r[üu]ckerstattung\w*|erstatt\w+|entsch[äa]digung\w*|schadens?ersatz\w*)\b", re.I)),
    ("SLA credit or penalty demanded", re.compile(
        r"\b(sla (credit|breach|penalt\w+|violation)|service credit|penalty clause|"
        r"vertragsstrafe\w*|sla[- ]?(gutschrift|verletzung))\b", re.I)),
    ("legal action or escalation threatened", re.compile(
        r"\b(lawyer|attorney|legal (action|team|department)|sue |lawsuit|litigation|gdpr complaint|"
        r"anwalt\w*|rechtsanwalt\w*|klage\w*|rechtliche schritte|datenschutzbeh[öo]rde)\b", re.I)),
    ("contract cancellation or termination", re.compile(
        r"\b(cancel (my|our|the) (contract|subscription|plan|account)|terminate (my|our|the) (contract|agreement)|"
        r"k[üu]ndig\w+|vertrag\w* (k[üu]ndigen|aufl[öo]sen))\b", re.I)),
    ("pricing or discount commitment requested", re.compile(
        r"\b(guarantee\w* (price|pricing|discount)|price match|waive (the )?fee|"
        r"preisnachlass\w*|rabatt zusichern|geb[üu]hr erlassen)\b", re.I)),
    ("credentials or account takeover request", re.compile(
        r"\b(send (me )?(my|the) password|reset .{0,20}password for (another|someone)|"
        r"give me (admin|root) access|passwort .{0,20}zusenden)\b", re.I)),
]


@dataclass
class GateOutcome:
    decision: EscalationDecision
    reasons: list[str]

    @property
    def escalate(self) -> bool:
        return self.decision == "ESCALATE"


def commitment_requests(text: str) -> list[str]:
    """R5 hits: what the ticket is demanding that only a human can promise."""
    return [label for label, pattern in COMMITMENT_PATTERNS if pattern.search(text or "")]


def pre_draft_gate(
    predicted_type: str,
    predicted_priority: str,
    triage_confidence: float,
    high_priority_probability: float,
    top_similarity: float,
    ticket_text: str,
    *,
    triage_confidence_min: float = TRIAGE_CONFIDENCE_MIN,
    retrieval_similarity_min: float = RETRIEVAL_SIMILARITY_MIN,
    high_priority_alert_probability: float = HIGH_PRIORITY_ALERT_PROBABILITY,
) -> GateOutcome:
    reasons: list[str] = []

    if predicted_priority == "high" and predicted_type == "Incident":
        reasons.append("R1 high-priority Incident: page the on-call engineer")
    elif high_priority_probability >= high_priority_alert_probability:
        reasons.append(
            f"R2 possible missed outage: P(high)={high_priority_probability:.2f} "
            f">= {high_priority_alert_probability:.2f} although the top label is '{predicted_priority}'"
        )

    if triage_confidence < triage_confidence_min:
        reasons.append(
            f"R3 low triage confidence {triage_confidence:.2f} < {triage_confidence_min:.2f}"
        )
    if top_similarity < retrieval_similarity_min:
        reasons.append(
            f"R4 no historical precedent: best similarity {top_similarity:.2f} < {retrieval_similarity_min:.2f}"
        )
    for hit in commitment_requests(ticket_text):
        reasons.append(f"R5 out of scope for an AI reply: {hit}")

    return GateOutcome("ESCALATE" if reasons else "AUTO_DRAFT", reasons)


def post_draft_gate(outcome: GateOutcome, grounded: bool, refused: bool, refusal_reason: str = "") -> GateOutcome:
    """R6: a draft nobody can verify is not sendable, however fluent it reads."""
    reasons = list(outcome.reasons)
    if refused:
        reasons.append(f"R6 model refused for lack of precedent: {refusal_reason or 'no supporting resolution'}")
    elif not grounded:
        reasons.append("R6 ungrounded draft: no cited quote was found verbatim in a retrieved resolution")
    return GateOutcome("ESCALATE" if reasons else "AUTO_DRAFT", reasons)


_PAGE_ONCALL_RULES = frozenset({"R1", "R2", "R5", "R7"})
_AGENT_REVIEW_RULES = frozenset({"R3", "R4", "R6"})
_RULE_CODE_RE = re.compile(r"^(R\d+)\b", re.IGNORECASE)


def _parse_rule_code(reason: str) -> str | None:
    """Extract the leading rule code (e.g. 'R1') from an escalation reason string."""
    match = _RULE_CODE_RE.match((reason or "").strip())
    return match.group(1).upper() if match else None


def decide_tier(decision: EscalationDecision, reasons: list[str]) -> Tier:
    """Three-tier gate (N1). Owner: E (Kaushik).

    Maps escalation reasons to a handling tier:
    - no reasons -> "AUTO_DRAFT"
    - any of R1, R2, R5, R7 -> "PAGE_ONCALL"
    - only R3, R4, R6 -> "AGENT_REVIEW"
    """
    if not reasons:
        return "AUTO_DRAFT"
    codes = {_parse_rule_code(reason) for reason in reasons}
    if codes & _PAGE_ONCALL_RULES:
        return "PAGE_ONCALL"
    if codes <= _AGENT_REVIEW_RULES:
        return "AGENT_REVIEW"
    return "PAGE_ONCALL"
