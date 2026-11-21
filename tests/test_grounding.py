"""Claim-vs-quote checks (audit H1) and locator precision."""

import pytest

from agent.grounding import check_claim, ground, refine_locator
from memory.chunking import make_chunk
from shared.contracts import DraftAnswer, DraftFinding, RetrievedChunk

QUOTE = "Reported potholes are repaired within two business days."


@pytest.mark.parametrize("claim, why", [
    ("Potholes are never repaired; residents must fix them at their own cost.", "polarity"),  # the audit probe
    ("Potholes are repaired within five business days.", "5"),
    ("Potholes are repaired within 3 business days.", "3"),
    ("Potholes are not repaired within two business days.", "polarity"),
    ("Potholes aren't fixed within two business days.", "polarity"),
    ("The library is open on Sundays.", "no wording"),
])
def test_mismatched_claims_are_rejected(claim, why):
    reason = check_claim(claim, QUOTE)
    assert reason and why in reason


@pytest.mark.parametrize("claim, quote", [
    (QUOTE, QUOTE),                                                   # extractive baseline: claim == quote
    ("Potholes get repaired within 2 business days.", QUOTE),        # digits vs number words
    ("Repairs happen within two business days of a report.", QUOTE),  # light stemming
    ("No, an occupancy permit cannot exceed 30 days.", "Street occupancy permits cannot exceed 30 days."),
    ("Parking is not allowed on snow routes.", "Do not park on posted snow emergency routes."),
    ("The cafe permit fee is $150.", "SIDEWALK_CAFE_FEE = 150"),
    ("Sidewalks must be cleared within 6 hours.", "must be cleared within 6 hours after snowfall ends"),
])
def test_faithful_claims_pass(claim, quote):
    assert check_claim(claim, quote) is None


def _ground(claim: str, quote: str = QUOTE, conf: float = 0.9):
    chunk = make_chunk("street_services.md", "doc", f"# Streets\n\n{QUOTE}\nCall 311.", "L1-L4", start_line=1)
    draft = DraftAnswer(findings=[DraftFinding(claim=claim, chunk_id=chunk.id, evidence_quote=quote,
                                               confidence_score=conf)])
    return ground(draft, [RetrievedChunk(chunk=chunk, score=1.0)], 0.5)


def test_ground_tags_rejection_kinds():
    assert _ground("Potholes are never repaired.")[1][0].kind == "claim_mismatch"
    assert _ground("x", quote="robots fix potholes overnight")[1][0].kind == "quote_not_found"
    assert _ground(QUOTE, conf=0.2)[1][0].kind == "low_confidence"
    findings, rejected = _ground("Potholes are repaired within 2 business days.")
    assert findings and not rejected


def test_same_named_files_in_different_roots_do_not_collide(tmp_path):
    from memory.common import rel_source

    (tmp_path / "dirA").mkdir()
    (tmp_path / "dirB").mkdir()
    a = rel_source(tmp_path / "dirA/readme.md", tmp_path / "dirA")
    b = rel_source(tmp_path / "dirB/readme.md", tmp_path / "dirB")
    assert (a, b) == ("dirA/readme.md", "dirB/readme.md")
    (tmp_path / "dirA/readme.md").write_text("x")
    assert rel_source(tmp_path / "dirA/readme.md", tmp_path / "dirA/readme.md") == "dirA/readme.md"


def test_locator_is_precise_even_when_case_and_spacing_differ():
    chunk = make_chunk("a.md", "doc", "intro\n\nReported potholes are\nrepaired within two business days.",
                       "L10-L13", start_line=10)
    assert refine_locator(chunk, "REPORTED potholes are repaired") == "L12-L13"
    assert refine_locator(chunk, "intro") == "L10"
