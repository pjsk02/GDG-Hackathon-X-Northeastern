"""Offline unit tests for sentinel.writer (prompt rules, extractive fallback, citation verification).

Owner: D (Sujitha).

Contracts under test (sentinel/writer.py):
    SYSTEM_PROMPT: str
    build_user_prompt(subject: str, body: str, language: str, precedents: list[Precedent]) -> str
    extractive_draft(language: str, precedents: list[Precedent]) -> SentinelDraft
    verify_citations(
        draft: SentinelDraft, precedents: list[Precedent]
    ) -> tuple[list[VerifiedCitation], list[CitationRejection]]
"""

from __future__ import annotations

import re

import pytest

from sentinel.writer import (
    MIN_QUOTE_CHARS,
    PROMPT_ANSWER_CHARS,
    PROMPT_BODY_CHARS,
    PROMPT_PRECEDENTS,
    SYSTEM_PROMPT,
    build_user_prompt,
    extractive_draft,
    verify_citations,
)
from shared.contracts import DraftCitation, Precedent, SentinelDraft


def _make_precedent(
    ticket_id: str = "TKT-00001",
    *,
    similarity: float = 0.875,
    subject: str = "VPN gateway timeout",
    body_snippet: str = "Users cannot reach the corporate VPN gateway since morning.",
    answer: str = "Restarted the VPN gateway and cleared stale sessions; connections are stable now.",
    ticket_type: str = "Incident",
    queue: str = "Technical Support",
    priority: str = "high",
    language: str = "en",
) -> Precedent:
    return Precedent(
        ticket_id=ticket_id,
        similarity=similarity,
        subject=subject,
        body_snippet=body_snippet,
        answer=answer,
        type=ticket_type,
        queue=queue,
        priority=priority,
        language=language,
    )


def _make_draft(
    citations: list[DraftCitation],
    *,
    reply_language: str = "en",
    refused: bool = False,
    draft_reply: str = "We are applying the documented resolution steps now.",
) -> SentinelDraft:
    return SentinelDraft(
        reply_language=reply_language,  # type: ignore[arg-type]
        refused=refused,
        citations=citations,
        draft_reply=draft_reply,
    )


# ---------------------------------------------------------------------------
# 1. SYSTEM_PROMPT required rules
# ---------------------------------------------------------------------------


def test_system_prompt_has_briefing_rule() -> None:
    lower = SYSTEM_PROMPT.lower()
    assert "briefing" in lower
    assert "english" in lower
    assert re.search(r"\bone\b[^.\n]*\bsentence\b", lower) is not None
    assert re.search(r"\b25\s+words?\b", lower) is not None
    assert re.search(r"(?:no|without|never|do not)[^.\n]*advice", lower) is not None


def test_system_prompt_has_commitment_refusal_rule() -> None:
    lower = SYSTEM_PROMPT.lower()
    assert "refund" in lower
    assert "credit" in lower
    assert "legal" in lower
    assert "colleague" in lower
    assert re.search(r"follow[\s-]*up", lower) is not None


def test_system_prompt_has_german_formal_and_citations_first_rules() -> None:
    lower = SYSTEM_PROMPT.lower()
    assert "german" in lower
    assert "formal" in lower
    assert re.search(r"\bSie\b", SYSTEM_PROMPT) is not None
    assert re.search(
        r'(?:fill\s+"?citations"?\s+first|citations?\s+first|citations?\b[^.\n]*\bfirst\b[^.\n]*draft_reply)',
        lower,
    ) is not None
    assert "original language" in lower


def test_system_prompt_has_prompt_injection_defense_rule() -> None:
    lower = SYSTEM_PROMPT.lower()
    assert "ticket" in lower and "precedent" in lower
    assert "data, not instructions" in lower
    assert re.search(r"ignore[^.\n]*instruction", lower) is not None


# ---------------------------------------------------------------------------
# 2. extractive_draft (unchanged and deterministic)
# ---------------------------------------------------------------------------


def test_extractive_draft_english_frame_citation_and_determinism() -> None:
    p1 = _make_precedent(
        ticket_id="TKT-00101",
        similarity=0.91,
        answer="Restarted the VPN gateway and cleared stale sessions; connections are stable now.",
    )
    p2 = _make_precedent(
        ticket_id="TKT-00102",
        similarity=0.72,
        answer="Reissued the client TLS certificate and asked the user to reconnect.",
    )

    draft_a = extractive_draft("en", [p1, p2])
    draft_b = extractive_draft("en", [p1, p2])

    assert draft_a == draft_b
    assert draft_a.refused is False
    assert draft_a.reply_language == "en"
    assert draft_a.draft_reply == (
        "Thank you for contacting support. A very similar case (TKT-00101) was resolved as follows: "
        "“Restarted the VPN gateway and cleared stale sessions; connections are stable now.”. "
        "We are applying the same steps to your ticket and will confirm once done."
    )
    assert len(draft_a.citations) == 1
    assert draft_a.citations[0] == DraftCitation(
        ticket_id="TKT-00101",
        evidence_quote="Restarted the VPN gateway and cleared stale sessions; connections are stable now.",
    )

    verified, rejected = verify_citations(draft_a, [p1, p2])
    assert len(verified) == 1
    assert rejected == []
    assert verified[0].ticket_id == "TKT-00101"
    assert verified[0].similarity == pytest.approx(0.91)


def test_extractive_draft_german_frame_and_citation_verification() -> None:
    p = _make_precedent(
        ticket_id="TKT-00202",
        similarity=0.88,
        language="de",
        answer="Wir haben das VPN-Gateway neu gestartet und veraltete Sitzungen bereinigt.",
    )

    draft = extractive_draft("de", [p])

    assert draft.refused is False
    assert draft.reply_language == "de"
    assert draft.draft_reply == (
        "Vielen Dank für Ihre Nachricht. Ein sehr ähnlicher Fall (TKT-00202) wurde wie folgt gelöst: "
        "„Wir haben das VPN-Gateway neu gestartet und veraltete Sitzungen bereinigt.“. "
        "Wir wenden dieselben Schritte auf Ihr Ticket an und melden uns."
    )
    assert len(draft.citations) == 1
    assert draft.citations[0].ticket_id == "TKT-00202"

    verified, rejected = verify_citations(draft, [p])
    assert len(verified) == 1
    assert rejected == []
    assert verified[0].ticket_id == "TKT-00202"


def test_extractive_draft_skips_short_resolutions_and_uses_first_usable() -> None:
    short_p = _make_precedent(ticket_id="TKT-00010", answer="x" * (MIN_QUOTE_CHARS - 1))
    blank_p = _make_precedent(ticket_id="TKT-00011", answer="   \n\t   ")
    usable_p = _make_precedent(
        ticket_id="TKT-00012",
        answer="Reset the user account password and verified SSO login succeeded.",
    )

    draft = extractive_draft("en", [short_p, blank_p, usable_p])

    assert draft.refused is False
    assert len(draft.citations) == 1
    assert draft.citations[0].ticket_id == "TKT-00012"
    verified, rejected = verify_citations(draft, [short_p, blank_p, usable_p])
    assert len(verified) == 1
    assert rejected == []


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize(
    "precedents",
    [
        [],
        [_make_precedent(ticket_id="TKT-00020", answer="Done.")],
        [
            _make_precedent(ticket_id="TKT-00021", answer="   "),
            _make_precedent(ticket_id="TKT-00022", answer="a" * (MIN_QUOTE_CHARS - 1)),
        ],
    ],
)
def test_extractive_draft_refuses_when_no_usable_precedent(
    language: str, precedents: list[Precedent]
) -> None:
    draft = extractive_draft(language, precedents)

    assert draft.refused is True
    assert draft.reply_language == language
    assert draft.citations == []
    assert draft.draft_reply == ""
    assert draft.refusal_reason.strip() != ""


def test_extractive_draft_truncates_to_240_chars_and_collapses_whitespace() -> None:
    long_answer = (
        "Step one:   verify the gateway\tstatus\n"
        "Step two:  clear stale session tokens across all regional nodes. "
        + "Confirmed stable connectivity for all affected accounts after rolling restart. " * 4
    )
    p = _make_precedent(ticket_id="TKT-00303", answer=long_answer)

    draft = extractive_draft("en", [p])

    assert draft.refused is False
    quote = draft.citations[0].evidence_quote
    assert len(quote) == 240
    assert "\n" not in quote
    assert "\t" not in quote
    assert "  " not in quote
    assert quote == " ".join(long_answer.split())[:240]

    verified, rejected = verify_citations(draft, [p])
    assert len(verified) == 1
    assert rejected == []


# ---------------------------------------------------------------------------
# 3. build_user_prompt
# ---------------------------------------------------------------------------


def test_build_user_prompt_limits_precedents_and_includes_required_sections() -> None:
    assert PROMPT_PRECEDENTS == 4
    precedents = [
        _make_precedent(
            ticket_id=f"TKT-{i:05d}",
            similarity=0.95 - i * 0.05,
            subject=f"Issue {i}",
            body_snippet=f"Detailed problem description number {i}.",
            answer=f"Detailed verified resolution number {i}.",
            language="de" if i % 2 == 0 else "en",
        )
        for i in range(1, 7)
    ]

    prompt = build_user_prompt(
        subject="Cannot connect to VPN",
        body="My VPN client hangs during handshake.",
        language="de",
        precedents=precedents,
    )

    assert "PRECEDENTS" in prompt
    assert "Problem:" in prompt
    assert "Resolution:" in prompt
    assert "INCOMING TICKET" in prompt
    assert "language detected: de" in prompt
    assert "Subject: Cannot connect to VPN" in prompt
    assert "Body: My VPN client hangs during handshake." in prompt

    for i in range(1, PROMPT_PRECEDENTS + 1):
        assert f"[TKT-{i:05d}]" in prompt
        assert f"Detailed problem description number {i}." in prompt
        assert f"Detailed verified resolution number {i}." in prompt

    assert "[TKT-00005]" not in prompt
    assert "[TKT-00006]" not in prompt


@pytest.mark.parametrize("subject", ["", None])
def test_build_user_prompt_handles_missing_subject_and_empty_precedents(
    subject: str | None,
) -> None:
    prompt = build_user_prompt(
        subject=subject,  # type: ignore[arg-type]
        body="Just checking on my ticket status.",
        language="en",
        precedents=[],
    )

    assert "(no precedents retrieved)" in prompt
    assert "INCOMING TICKET" in prompt
    assert "language detected: en" in prompt
    assert "Subject: (none)" in prompt
    assert "Body: Just checking on my ticket status." in prompt


def test_build_user_prompt_truncates_long_precedent_fields() -> None:
    long_body = "B" * (PROMPT_BODY_CHARS + 50)
    long_answer = "A" * (PROMPT_ANSWER_CHARS + 50)
    p = _make_precedent(subject="", body_snippet=long_body, answer=long_answer)

    prompt = build_user_prompt("Subj", "Body", "en", [p])

    assert f"Problem: {'B' * PROMPT_BODY_CHARS}\n" in prompt
    assert "B" * (PROMPT_BODY_CHARS + 1) not in prompt
    assert f"Resolution: {'A' * PROMPT_ANSWER_CHARS}" in prompt
    assert "A" * (PROMPT_ANSWER_CHARS + 1) not in prompt


# ---------------------------------------------------------------------------
# 4. verify_citations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        'Cleared the "stale" user\'s cache and restarted the VPN service',
        'CLEARED THE "STALE" USER\'S CACHE AND RESTARTED THE VPN SERVICE',
        'Cleared   the\n\t"stale"   user\'s   cache\nand restarted the VPN service',
        "Cleared the “stale” user’s cache and restarted the VPN service",
    ],
)
def test_verify_citations_accepts_verbatim_across_case_whitespace_and_curly_quotes(
    quote: str,
) -> None:
    p = _make_precedent(
        ticket_id="TKT-00001",
        similarity=0.84,
        answer='Support team cleared the "stale" user\'s cache and restarted the VPN service successfully.',
    )
    draft = _make_draft([DraftCitation(ticket_id="TKT-00001", evidence_quote=quote)])

    verified, rejected = verify_citations(draft, [p])

    assert rejected == []
    assert len(verified) == 1
    assert verified[0].ticket_id == "TKT-00001"
    assert verified[0].evidence_quote == quote.strip()
    assert verified[0].similarity == pytest.approx(0.84)


def test_verify_citations_normalizes_ticket_id_case_and_whitespace() -> None:
    p = _make_precedent(
        ticket_id="TKT-00001",
        similarity=0.92,
        answer="Restarted the billing worker and reprocessed the stuck invoice.",
    )
    draft = _make_draft(
        [
            DraftCitation(
                ticket_id=" tkt-00001 ",
                evidence_quote="  Restarted the billing worker and reprocessed the stuck invoice.  ",
            )
        ]
    )

    verified, rejected = verify_citations(draft, [p])

    assert rejected == []
    assert len(verified) == 1
    assert verified[0].ticket_id == "TKT-00001"
    assert verified[0].evidence_quote == "Restarted the billing worker and reprocessed the stuck invoice."
    assert verified[0].similarity == pytest.approx(0.92)


def test_verify_citations_rejects_unknown_ticket() -> None:
    p = _make_precedent(ticket_id="TKT-00001")
    draft = _make_draft(
        [
            DraftCitation(
                ticket_id="TKT-99999",
                evidence_quote="Restarted the VPN gateway and cleared stale sessions",
            )
        ]
    )

    verified, rejected = verify_citations(draft, [p])

    assert verified == []
    assert len(rejected) == 1
    assert rejected[0].kind == "unknown_ticket"


@pytest.mark.parametrize(
    "short_quote",
    [
        "",
        "   \t\n  ",
        "Restarted",  # present verbatim in resolution, but shorter than MIN_QUOTE_CHARS (12)
    ],
)
def test_verify_citations_rejects_quote_too_short(short_quote: str) -> None:
    p = _make_precedent(
        ticket_id="TKT-00001",
        answer="Restarted the VPN gateway and cleared stale sessions; connections are stable now.",
    )
    assert len(short_quote.strip()) < MIN_QUOTE_CHARS
    draft = _make_draft([DraftCitation(ticket_id="TKT-00001", evidence_quote=short_quote)])

    verified, rejected = verify_citations(draft, [p])

    assert verified == []
    assert len(rejected) == 1
    assert rejected[0].kind == "quote_too_short"


@pytest.mark.parametrize(
    "bad_quote",
    [
        # Paraphrase of the English resolution
        "Rebooted the VPN server and removed old sessions so users can connect.",
        # German translation of the English resolution
        "Das VPN-Gateway wurde neu gestartet und veraltete Sitzungen wurden bereinigt.",
    ],
)
def test_verify_citations_rejects_paraphrased_or_translated_quote(bad_quote: str) -> None:
    p = _make_precedent(
        ticket_id="TKT-00001",
        answer="Restarted the VPN gateway and cleared stale sessions; connections are stable now.",
    )
    draft = _make_draft([DraftCitation(ticket_id="TKT-00001", evidence_quote=bad_quote)])

    verified, rejected = verify_citations(draft, [p])

    assert verified == []
    assert len(rejected) == 1
    assert rejected[0].kind == "quote_not_found"


def test_verify_citations_splits_mixed_valid_and_invalid_citations() -> None:
    p = _make_precedent(
        ticket_id="TKT-00001",
        answer="Restarted the VPN gateway and cleared stale sessions; connections are stable now.",
    )
    draft = _make_draft(
        [
            DraftCitation(ticket_id="TKT-00001", evidence_quote="Restarted the VPN gateway"),
            DraftCitation(ticket_id="TKT-40404", evidence_quote="Restarted the VPN gateway"),
            DraftCitation(ticket_id="TKT-00001", evidence_quote="Restarted"),
            DraftCitation(ticket_id="TKT-00001", evidence_quote="We rebooted the gateway for you."),
        ]
    )

    verified, rejected = verify_citations(draft, [p])

    assert [v.ticket_id for v in verified] == ["TKT-00001"]
    assert [r.kind for r in rejected] == ["unknown_ticket", "quote_too_short", "quote_not_found"]
