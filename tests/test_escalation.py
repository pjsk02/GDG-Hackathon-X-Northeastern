"""Tests for the three-tier safety gate in sentinel/escalation.py."""

from __future__ import annotations

import pytest

from sentinel.escalation import decide_tier, post_draft_gate, pre_draft_gate


@pytest.mark.parametrize(
    ("reason", "expected_tier"),
    [
        ("R1 high-priority Incident: page the on-call engineer", "PAGE_ONCALL"),
        ("R2 possible missed outage: P(high)=0.60 >= 0.50", "PAGE_ONCALL"),
        ("R3 low triage confidence 0.40 < 0.55", "AGENT_REVIEW"),
        ("R4 no historical precedent: best similarity 0.30 < 0.55", "AGENT_REVIEW"),
        ("R5 out of scope for an AI reply: refund or compensation demanded", "PAGE_ONCALL"),
        ("R6 ungrounded draft: no cited quote was found verbatim", "AGENT_REVIEW"),
        ("R7 prompt injection detected", "PAGE_ONCALL"),
    ],
)
def test_decide_tier_single_rules(reason: str, expected_tier: str):
    assert decide_tier("ESCALATE", [reason]) == expected_tier


def test_decide_tier_no_reasons_is_auto_draft():
    assert decide_tier("AUTO_DRAFT", []) == "AUTO_DRAFT"


def test_decide_tier_mixes_page_oncall_wins_over_agent_review():
    assert decide_tier("ESCALATE", [
        "R3 low triage confidence 0.40 < 0.55",
        "R1 high-priority Incident: page the on-call engineer",
    ]) == "PAGE_ONCALL"
    assert decide_tier("ESCALATE", [
        "R4 no historical precedent: best similarity 0.20 < 0.55",
        "R5 out of scope for an AI reply: SLA credit or penalty demanded",
        "R6 ungrounded draft: no cited quote was found verbatim",
    ]) == "PAGE_ONCALL"
    assert decide_tier("ESCALATE", [
        "R3 low triage confidence 0.40 < 0.55",
        "R7 prompt injection detected",
    ]) == "PAGE_ONCALL"


def test_decide_tier_only_agent_review_rules():
    assert decide_tier("ESCALATE", [
        "R3 low triage confidence 0.40 < 0.55",
        "R4 no historical precedent: best similarity 0.30 < 0.55",
        "R6 ungrounded draft: no cited quote was found verbatim",
    ]) == "AGENT_REVIEW"


def test_decide_tier_parses_leading_code_with_whitespace_or_colon():
    assert decide_tier("ESCALATE", ["  r3: low confidence"]) == "AGENT_REVIEW"
    assert decide_tier("ESCALATE", ["R2: high P(high)"]) == "PAGE_ONCALL"


def test_gate_integration_maps_to_expected_tiers():
    clean = pre_draft_gate("Request", "low", 0.9, 0.05, 0.85, "How do I reset MFA?")
    assert decide_tier(clean.decision, clean.reasons) == "AUTO_DRAFT"

    low_conf = pre_draft_gate("Request", "low", 0.3, 0.05, 0.85, "How do I reset MFA?")
    assert decide_tier(low_conf.decision, low_conf.reasons) == "AGENT_REVIEW"

    ungrounded = post_draft_gate(clean, grounded=False, refused=False)
    assert decide_tier(ungrounded.decision, ungrounded.reasons) == "AGENT_REVIEW"

    incident = pre_draft_gate("Incident", "high", 0.9, 0.9, 0.85, "Production API is down")
    assert decide_tier(incident.decision, incident.reasons) == "PAGE_ONCALL"

    refund = pre_draft_gate("Request", "low", 0.9, 0.05, 0.85, "Give me a full refund now")
    assert decide_tier(refund.decision, refund.reasons) == "PAGE_ONCALL"
