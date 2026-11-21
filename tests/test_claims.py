"""Offline unit tests for sentinel.claims.check_claims (number-and-promise guard N4).

Owner: D (Sujitha).

Contract under test:
    check_claims(reply: str, verified: list[VerifiedCitation]) -> list[GuardFinding]

Every number, money amount, percentage, date/duration, and promise phrase (English and German)
in `reply` must be backed by at least one verified citation quote (case- and whitespace-insensitive);
otherwise it is returned as a `GuardFinding`. Ticket IDs (e.g. TKT-01234) and PII placeholders
(e.g. <IPV4>, <EMAIL>) are ignored.
"""

from __future__ import annotations

import pytest

from sentinel.claims import check_claims
from sentinel.writer import extractive_draft, verify_citations
from shared.contracts import GuardFinding, Precedent, VerifiedCitation


def _cite(
    quote: str,
    ticket_id: str = "TKT-00001",
    similarity: float = 0.8,
) -> VerifiedCitation:
    return VerifiedCitation(
        ticket_id=ticket_id,
        evidence_quote=quote,
        similarity=similarity,
    )


def _precedent(
    ticket_id: str,
    answer: str,
    language: str,
) -> Precedent:
    return Precedent(
        ticket_id=ticket_id,
        similarity=0.88,
        subject="Billing and SLA follow-up",
        body_snippet="Customer requested status and adjustment details.",
        answer=answer,
        type="Request",
        queue="Billing and Payments",
        priority="medium",
        language=language,
    )


def _assert_valid_findings(findings: list[GuardFinding]) -> None:
    assert all(isinstance(f, GuardFinding) for f in findings)
    assert all(f.text.strip() for f in findings)
    assert all(f.reason.strip() for f in findings)


# 1. Empty / whitespace reply -> []
@pytest.mark.parametrize("reply", ["", "   ", "\n\t  \n"])
def test_empty_and_whitespace_replies_return_no_findings(reply: str) -> None:
    assert check_claims(reply, []) == []
    assert check_claims(reply, [_cite("Restarted the VPN gateway.")]) == []


# 2. Clean reply with no numbers/dates/money/promises -> []
@pytest.mark.parametrize(
    "reply",
    [
        "Thank you for contacting support. We restarted the VPN gateway and cleared stale sessions.",
        "Vielen Dank für Ihre Nachricht. Wir haben den Dienst neu gestartet und die Verbindung geprüft.",
    ],
)
def test_clean_reply_without_claims_passes(reply: str) -> None:
    assert check_claims(reply, []) == []


# 3. Ticket IDs are ignored even when not in quotes -> []
def test_ticket_ids_are_ignored_even_when_unbacked() -> None:
    reply = (
        "We reviewed similar cases TKT-01234 and TKT-99999 and applied the same configuration fix."
    )
    assert check_claims(reply, []) == []
    assert check_claims(reply, [_cite("Applied the standard configuration fix.")]) == []


# 4. PII placeholders are ignored -> []
def test_pii_placeholders_are_ignored() -> None:
    reply = "Please verify connectivity from <IPV4> and forward the diagnostic log to <EMAIL>."
    assert check_claims(reply, []) == []


# 5. Unbacked EN money -> flagged as kind == "money"
@pytest.mark.parametrize(
    "reply",
    [
        "The invoice adjustment is $500.",
        "The invoice total is 5000 EUR.",
        "The recorded charge is 100 USD.",
    ],
)
def test_unbacked_en_money_is_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    kinds = [f.kind for f in findings]
    assert "money" in kinds
    assert "number" not in kinds


# 6. Backed EN/DE money -> []
@pytest.mark.parametrize(
    ("reply", "quote"),
    [
        ("The invoice adjustment is €50.", "Billing team refunded € 50 to the customer."),
        ("The invoice total is 500 EUR.", "Confirmed the invoice total of 500 EUR in billing."),
        ("Der Rechnungsbetrag beträgt 250 €.", "Der Rechnungsbetrag von 250 € wurde verbucht."),
        ("Die Gebühr beträgt 19,99 EUR.", "Die einmalige Gebühr von 19,99 eur wurde hinterlegt."),
    ],
)
def test_backed_en_and_de_money_passes(reply: str, quote: str) -> None:
    assert check_claims(reply, [_cite(quote)]) == []


# 7. Unbacked DE money -> flagged as kind == "money"
@pytest.mark.parametrize(
    "reply",
    [
        "Der offene Betrag liegt bei 250 €.",
        "Die Gebühr beträgt 19,99 EUR.",
    ],
)
def test_unbacked_de_money_is_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    kinds = [f.kind for f in findings]
    assert "money" in kinds
    assert "number" not in kinds


# 8. Unbacked and backed percentages EN & DE
@pytest.mark.parametrize(
    "reply",
    [
        "The service maintained 99.9% availability.",
        "Die Auslastung sank um 15 Prozent.",
    ],
)
def test_unbacked_en_and_de_percent_is_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    kinds = [f.kind for f in findings]
    assert "percent" in kinds
    assert "number" not in kinds


@pytest.mark.parametrize(
    ("reply", "quote"),
    [
        (
            "The service maintained 99.9% availability.",
            "Measured 99.9% availability over the quarter.",
        ),
        (
            "Die Auslastung sank um 15 Prozent.",
            "Nach dem Patch sank die Auslastung um 15 prozent.",
        ),
    ],
)
def test_backed_en_and_de_percent_passes(reply: str, quote: str) -> None:
    assert check_claims(reply, [_cite(quote)]) == []


# 9. Unbacked EN durations/dates -> flagged as kind == "date"
@pytest.mark.parametrize(
    "reply",
    [
        "The cache refreshes after 24 hours.",
        "You will receive an update within 2 days.",
        "The maintenance window closes by Friday.",
        "The certificate expires on 2026-11-21.",
    ],
)
def test_unbacked_en_dates_and_durations_are_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    kinds = [f.kind for f in findings]
    assert "date" in kinds
    assert "number" not in kinds


# 10. Backed EN duration (case- and whitespace-insensitive) -> []
@pytest.mark.parametrize(
    ("reply", "quote"),
    [
        (
            "You will receive an update within 2 days.",
            "Customers receive an update   WITHIN   2   DAYS  after escalation.",
        ),
        (
            "The cache refreshes after 24 hours.",
            "DNS cache entries expire automatically after 24   HOURS.",
        ),
    ],
)
def test_backed_en_duration_passes_case_and_whitespace_insensitive(
    reply: str, quote: str
) -> None:
    assert check_claims(reply, [_cite(quote)]) == []


# 11. Unbacked DE durations/dates -> flagged as kind == "date"
@pytest.mark.parametrize(
    "reply",
    [
        "Die Synchronisation dauert 48 Stunden.",
        "Das Update erfolgt bis Freitag.",
        "Die Bearbeitung erfolgt innerhalb von 3 Werktagen.",
        "Der Wartungstermin ist am 21.11.2026.",
    ],
)
def test_unbacked_de_dates_and_durations_are_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    kinds = [f.kind for f in findings]
    assert "date" in kinds
    assert "number" not in kinds


# 12. Backed DE duration/date -> []
@pytest.mark.parametrize(
    ("reply", "quote"),
    [
        (
            "Die Synchronisation dauert 48 Stunden.",
            "Die vollständige Synchronisation dauert 48   STUNDEN.",
        ),
        (
            "Das Update erfolgt bis Freitag.",
            "Laut Wartungsplan wird der Patch bis   freitag eingespielt.",
        ),
    ],
)
def test_backed_de_dates_and_durations_pass(reply: str, quote: str) -> None:
    assert check_claims(reply, [_cite(quote)]) == []


# 13. Unbacked EN promises -> flagged as kind == "promise"
@pytest.mark.parametrize(
    "reply",
    [
        "We guarantee stable connectivity after this change.",
        "Your case qualifies for a full refund.",
        "The replacement hardware is provided free of charge.",
    ],
)
def test_unbacked_en_promises_are_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    assert any(f.kind == "promise" for f in findings)


# 14. Backed EN promise -> []
def test_backed_en_promise_passes() -> None:
    reply = "The replacement hardware is provided free of charge."
    quote = "Defective adapters are replaced FREE OF CHARGE under hardware support."
    assert check_claims(reply, [_cite(quote)]) == []


# 15. Unbacked DE promises -> flagged as kind == "promise"
@pytest.mark.parametrize(
    "reply",
    [
        "Wir erstatten den offenen Betrag auf Ihr Konto.",
        "Der Austausch erfolgt für Sie kostenlos.",
        "Wir garantieren eine stabile Verbindung nach dem Neustart.",
        "Sie erhalten eine vollständige Rückerstattung für den Ausfall.",
    ],
)
def test_unbacked_de_promises_are_flagged(reply: str) -> None:
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    assert any(f.kind == "promise" for f in findings)


# 16. Backed DE promise -> []
def test_backed_de_promise_passes() -> None:
    reply = "Der Austausch erfolgt für Sie kostenlos."
    quote = "Ein defektes Netzteil wird für Kunden KOSTENLOS ausgetauscht."
    assert check_claims(reply, [_cite(quote)]) == []


# 17. Standalone number unbacked & partial-digit trap (5 vs 50)
def test_unbacked_standalone_number_is_flagged() -> None:
    findings = check_claims("We activated 5 licenses for your team.", [])
    _assert_valid_findings(findings)
    assert any(f.kind == "number" and "5" in f.text for f in findings)


def test_partial_digit_trap_flags_five_when_quote_only_has_fifty() -> None:
    reply = "We restarted 5 servers in the cluster."
    quote = "We restarted 50 servers in the cluster."
    findings = check_claims(reply, [_cite(quote)])
    _assert_valid_findings(findings)
    assert any(f.kind == "number" and "5" in f.text for f in findings)


def test_backed_standalone_number_passes() -> None:
    reply = "We activated 5 licenses for your team."
    quote = "Provisioned 5 licenses for the engineering group."
    assert check_claims(reply, [_cite(quote)]) == []


# 18. Combined claim: promise + money + date without duplicating numbers
def test_combined_claim_flags_promise_money_and_date_without_duplicate_numbers() -> None:
    reply = "We guarantee a full refund of 500 EUR within 24 hours."
    findings = check_claims(reply, [])
    _assert_valid_findings(findings)
    kinds = {f.kind for f in findings}
    assert {"promise", "money", "date"}.issubset(kinds)
    assert "number" not in kinds


# 19. Multiple verified citations: claim backed by the second citation passes
def test_claim_backed_by_second_verified_citation_passes() -> None:
    reply = "The migration takes 48 hours."
    verified = [
        _cite("Restarted the proxy service and cleared stale sessions.", ticket_id="TKT-00101"),
        _cite("Database migration takes 48 hours to complete.", ticket_id="TKT-00202"),
    ]
    assert check_claims(reply, verified) == []


def test_multiple_claims_spread_across_verified_citations_pass() -> None:
    reply = "The invoice adjustment is 150 EUR and synchronization takes 48 hours."
    verified = [
        _cite("An invoice adjustment of 150 EUR was posted.", ticket_id="TKT-00101"),
        _cite("Full synchronization takes 48 hours.", ticket_id="TKT-00202"),
    ]
    assert check_claims(reply, verified) == []


# 20. Extractive drafts (EN and DE) with numbers/money/dates pass with their verified citation
@pytest.mark.parametrize(
    ("language", "ticket_id", "resolution"),
    [
        (
            "en",
            "TKT-04201",
            "Issued a 50 EUR adjustment within 24 hours for 3 affected accounts on 2026-11-21.",
        ),
        (
            "de",
            "TKT-04202",
            "Eine Gutschrift über 50 EUR wurde innerhalb von 48 Stunden für 3 Konten am 21.11.2026 verbucht.",
        ),
    ],
)
def test_extractive_draft_with_numeric_claims_passes_check_claims(
    language: str,
    ticket_id: str,
    resolution: str,
) -> None:
    precedent = _precedent(ticket_id=ticket_id, answer=resolution, language=language)
    draft = extractive_draft(language, [precedent])
    assert not draft.refused
    verified, rejected = verify_citations(draft, [precedent])
    assert verified and not rejected
    assert check_claims(draft.draft_reply, verified) == []
