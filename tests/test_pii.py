"""Offline unit tests for sentinel.pii (Step 5: PII and "What the AI saw", B3).

Owner: D (Sujitha).

Contract under test:
    mask_spans(text: str) -> list[tuple[int, int, str]]
    mask_pii(text: str) -> tuple[str, dict[str, int]]
    has_pii(text: str) -> bool

Deterministic regex-based PII masking for prompts: detects EMAIL, IPV4, IBAN, CARD,
PHONE (German & US/international), ACCOUNT, ADDRESS (EN & DE), and URL while avoiding
false positives on dates, version numbers, invalid IPv4 addresses, ticket IDs, plain
account prose, and year/price ranges. `mask_spans` returns sorted, non-overlapping
`(start, end, label)` spans whose replacement with `<label>` matches `mask_pii`.
"""

from __future__ import annotations

from collections import Counter

import pytest

from sentinel import pii


def _reconstruct_from_spans(text: str, spans: list[tuple[int, int, str]]) -> str:
    """Rebuild masked text by replacing each (start, end, label) span with <label>."""
    parts: list[str] = []
    cursor = 0
    for start, end, label in spans:
        parts.append(text[cursor:start])
        parts.append(f"<{label}>")
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _assert_span_invariants(
    text: str,
) -> tuple[list[tuple[int, int, str]], str, dict[str, int]]:
    """Verify structural invariants of mask_spans and exact consistency with mask_pii/has_pii."""
    spans = pii.mask_spans(text)
    masked, counts = pii.mask_pii(text)

    assert isinstance(spans, list)
    assert isinstance(masked, str)
    assert isinstance(counts, dict)

    prev_start = -1
    prev_end = 0
    for span in spans:
        assert isinstance(span, tuple) and len(span) == 3
        start, end, label = span
        assert isinstance(start, int) and isinstance(end, int)
        assert isinstance(label, str) and bool(label.strip())
        assert 0 <= start < end <= len(text)
        assert start > prev_start
        assert prev_end <= start
        prev_start = start
        prev_end = end

    assert _reconstruct_from_spans(text, spans) == masked
    assert counts == dict(Counter(label for _, _, label in spans))
    assert pii.has_pii(text) is bool(spans)
    return spans, masked, counts


# ---------------------------------------------------------------------------
# 1. Empty / whitespace / clean text
# ---------------------------------------------------------------------------


def test_empty_string_returns_no_pii() -> None:
    assert pii.mask_spans("") == []
    assert pii.mask_pii("") == ("", {})
    assert pii.has_pii("") is False


@pytest.mark.parametrize("text", [" ", "   ", "\n\t  \n"])
def test_whitespace_only_returns_no_pii(text: str) -> None:
    spans, masked, counts = _assert_span_invariants(text)
    assert spans == []
    assert masked == text
    assert counts == {}


@pytest.mark.parametrize(
    "text",
    [
        "Hello world",
        "The printer on the 4th floor keeps jamming when printing double-sided.",
        "Sehr geehrtes Team, wir brauchen Hilfe beim Neustart des Druckers.",
        "Placeholders <EMAIL>, <PHONE>, <IPV4>, <IBAN>, <CARD>, <ACCOUNT>, <ADDRESS>, <URL>.",
    ],
)
def test_clean_text_returns_no_pii(text: str) -> None:
    spans, masked, counts = _assert_span_invariants(text)
    assert spans == []
    assert masked == text
    assert counts == {}


# ---------------------------------------------------------------------------
# 2. False-positive controls (MUST NOT mask)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(
            "Meeting on 2026-11-21 and 21.11.2026 or 11/21/2026 at 14:30.",
            id="dates-and-time",
        ),
        pytest.param(
            "Scheduled maintenance on 2025-12-31, 01.03.2026, and 03/15/2026.",
            id="dates-variants",
        ),
        pytest.param(
            "Upgraded from v1.2.3.4 to version 10.2.3.1 (Build 10.0.19045.4170) on Python 3.12.15.",
            id="version-numbers",
        ),
        pytest.param(
            "Error code 999.888.777.666 occurred.",
            id="invalid-ipv4-999",
        ),
        pytest.param(
            "Rejected malformed hosts 256.100.50.25 and 192.168.1.256.",
            id="invalid-ipv4-256",
        ),
        pytest.param(
            "Please check TKT-01234, TKT-98765432, SD-1042, and INC-20260315.",
            id="ticket-ids",
        ),
        pytest.param(
            "Please check my account settings and customer service history.",
            id="account-word-prose-en",
        ),
        pytest.param(
            "Bitte prüfen Sie mein Konto und unsere Einstellungen im Kundenbereich.",
            id="account-word-prose-de",
        ),
        pytest.param(
            "Budget for 2025-2026 is 1000-2000 EUR.",
            id="ranges-years-prices",
        ),
        pytest.param(
            "Support window 08:00-17:00 applies across 2024-2026.",
            id="time-and-year-ranges",
        ),
    ],
)
def test_false_positive_controls_are_not_masked(text: str) -> None:
    spans, masked, counts = _assert_span_invariants(text)
    assert spans == []
    assert masked == text
    assert counts == {}


# ---------------------------------------------------------------------------
# 3. German & US/international phone numbers (MUST mask as PHONE)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phone",
    [
        "+49 171 1234567",
        "+49 (0) 30 12345678",
        "0049 30 12345678",
        "030 / 12345678",
        "0171-1234567",
        "(089) 1234567",
        "+1 (617) 555-0134",
        "(617) 555-0134",
        "+1 617-555-0194",
    ],
)
def test_german_and_international_phones_masked_as_phone(phone: str) -> None:
    spans, masked, counts = _assert_span_invariants(phone)
    assert counts == {"PHONE": 1}
    assert masked == "<PHONE>"
    assert spans == [(0, len(phone), "PHONE")]

    sentence = f"Please reach me at {phone} before noon."
    s_spans, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"PHONE": 1}
    assert s_masked == "Please reach me at <PHONE> before noon."
    start, end, label = s_spans[0]
    assert label == "PHONE"
    assert sentence[start:end] == phone


# ---------------------------------------------------------------------------
# 4. German & EU IBANs (MUST mask as IBAN, not CARD/PHONE)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "iban",
    [
        "DE89 3704 0044 0532 0130 00",
        "DE89370400440532013000",
        "DE89-3704-0044-0532-0130-00",
        "AT61 1904 3002 3457 3201",
    ],
)
def test_german_and_eu_ibans_masked_as_iban_not_card_or_phone(iban: str) -> None:
    spans, masked, counts = _assert_span_invariants(iban)
    assert counts == {"IBAN": 1}
    assert "CARD" not in counts
    assert "PHONE" not in counts
    assert masked == "<IBAN>"
    assert spans == [(0, len(iban), "IBAN")]

    sentence = f"Direct debit IBAN: {iban} for monthly billing."
    s_spans, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"IBAN": 1}
    assert s_masked == "Direct debit IBAN: <IBAN> for monthly billing."
    start, end, label = s_spans[0]
    assert label == "IBAN"
    assert sentence[start:end] == iban


# ---------------------------------------------------------------------------
# 5. Street addresses EN & DE (MUST mask as ADDRESS)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "must_redact"),
    [
        ("Hauptstraße 42", ["Hauptstraße", "42"]),
        ("Berliner Str. 12a, 10115 Berlin", ["Berliner Str.", "12a"]),
        ("Musterweg 7", ["Musterweg", "7"]),
        ("360 Huntington Ave", ["360", "Huntington", "Ave"]),
        ("123 Main Street, Apt 4B", ["123", "Main Street"]),
    ],
)
def test_street_addresses_en_and_de_masked_as_address(
    address: str,
    must_redact: list[str],
) -> None:
    _, masked, counts = _assert_span_invariants(address)
    assert counts == {"ADDRESS": 1}
    assert "<ADDRESS>" in masked
    for token in must_redact:
        assert token not in masked

    sentence = f"Send replacement hardware to {address}. Thanks."
    _, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"ADDRESS": 1}
    assert "<ADDRESS>" in s_masked
    assert s_masked.startswith("Send replacement hardware to ")
    assert s_masked.endswith(". Thanks.")
    for token in must_redact:
        assert token not in s_masked


# ---------------------------------------------------------------------------
# 6. Emails, IPv4, Cards, Accounts, URLs
# ---------------------------------------------------------------------------


def test_emails_masked_as_email() -> None:
    email = "a.mueller@example-hospital.de"
    spans, masked, counts = _assert_span_invariants(email)
    assert counts == {"EMAIL": 1}
    assert masked == "<EMAIL>"
    assert spans == [(0, len(email), "EMAIL")]

    sentence = (
        "Update email from a.mueller@example-hospital.de "
        "to anna.mueller@example-hospital.de."
    )
    _, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"EMAIL": 2}
    assert s_masked == "Update email from <EMAIL> to <EMAIL>."


@pytest.mark.parametrize("ipv4", ["192.168.14.2", "10.24.8.15"])
def test_valid_ipv4_masked_as_ipv4(ipv4: str) -> None:
    spans, masked, counts = _assert_span_invariants(ipv4)
    assert counts == {"IPV4": 1}
    assert masked == "<IPV4>"
    assert spans == [(0, len(ipv4), "IPV4")]

    sentence = f"Allowlist gateway IP {ipv4} for VPN access."
    _, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"IPV4": 1}
    assert s_masked == "Allowlist gateway IP <IPV4> for VPN access."


@pytest.mark.parametrize("card", ["4532 1488 0343 6467", "4532-1488-0343-6467"])
def test_credit_cards_masked_as_card(card: str) -> None:
    spans, masked, counts = _assert_span_invariants(card)
    assert counts == {"CARD": 1}
    assert "PHONE" not in counts
    assert masked == "<CARD>"
    assert spans == [(0, len(card), "CARD")]

    sentence = f"Card {card} was charged twice."
    _, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"CARD": 1}
    assert s_masked == "Card <CARD> was charged twice."


@pytest.mark.parametrize(
    ("sample", "secret_id"),
    [
        ("account KUNDE-884213", "KUNDE-884213"),
        ("ACCT-774920", "ACCT-774920"),
        ("Kundennummer: 123456", "123456"),
    ],
)
def test_accounts_masked_as_account(sample: str, secret_id: str) -> None:
    _, masked, counts = _assert_span_invariants(sample)
    assert counts == {"ACCOUNT": 1}
    assert "<ACCOUNT>" in masked
    assert secret_id not in masked

    sentence = f"Billing discrepancy on {sample} since Monday."
    _, s_masked, s_counts = _assert_span_invariants(sentence)
    assert s_counts == {"ACCOUNT": 1}
    assert "<ACCOUNT>" in s_masked
    assert secret_id not in s_masked
    assert "PHONE" not in s_counts
    assert "CARD" not in s_counts


def test_url_masked_as_url_preserving_trailing_period() -> None:
    text = "See https://portal.example.com/status."
    spans, masked, counts = _assert_span_invariants(text)
    assert counts == {"URL": 1}
    assert masked == "See <URL>."
    start, end, label = spans[0]
    assert label == "URL"
    assert text[start:end] == "https://portal.example.com/status"


def test_http_url_in_sentence_masked_as_url() -> None:
    text = "Visit http://status.example.org/health?check=1 right now."
    spans, masked, counts = _assert_span_invariants(text)
    assert counts == {"URL": 1}
    assert masked == "Visit <URL> right now."
    start, end, label = spans[0]
    assert label == "URL"
    assert text[start:end] == "http://status.example.org/health?check=1"


# ---------------------------------------------------------------------------
# 7. mask_spans structural invariants on dense / tricky inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Clean text with TKT-01234 and 2026-11-21.",
        "a@b.de,+49 171 1234567,192.168.14.2,DE89 3704 0044 0532 0130 00",
        "Repeat: a.mueller@example-hospital.de and a.mueller@example-hospital.de.",
        "Digit-heavy email u.123456@example-hospital.de and URL https://portal.example.com/status.",
        "Card 4532 1488 0343 6467 next to IBAN DE89370400440532013000 and ACCT-774920.",
        "Ship to Hauptstraße 42 or 360 Huntington Ave and call (089) 1234567.",
    ],
)
def test_mask_spans_structural_invariants_and_reconstruction(text: str) -> None:
    _assert_span_invariants(text)


# ---------------------------------------------------------------------------
# 8. Mixed real-world tickets (eval cases & combined PII + non-PII)
# ---------------------------------------------------------------------------


def test_mixed_real_world_ticket_masks_all_pii_and_preserves_non_pii() -> None:
    text = (
        "Ref TKT-01234 (opened 2026-11-21, app v2.4.1.0): "
        "Please update account KUNDE-884213 for a.mueller@example-hospital.de, "
        "phone +49 171 1234567, office IP 192.168.14.2, "
        "IBAN DE89 3704 0044 0532 0130 00, and address Berliner Str. 12a, 10115 Berlin."
    )
    spans, masked, counts = _assert_span_invariants(text)

    assert counts == {
        "ACCOUNT": 1,
        "EMAIL": 1,
        "PHONE": 1,
        "IPV4": 1,
        "IBAN": 1,
        "ADDRESS": 1,
    }
    for placeholder in (
        "<ACCOUNT>",
        "<EMAIL>",
        "<PHONE>",
        "<IPV4>",
        "<IBAN>",
        "<ADDRESS>",
    ):
        assert placeholder in masked

    # Non-PII operational identifiers must remain untouched.
    assert "TKT-01234" in masked
    assert "2026-11-21" in masked
    assert "v2.4.1.0" in masked

    # Raw PII must not leak into the masked prompt.
    for secret in (
        "KUNDE-884213",
        "a.mueller@example-hospital.de",
        "1234567",
        "192.168.14.2",
        "DE89",
        "0130",
        "Berliner Str.",
    ):
        assert secret not in masked

    # Exact span slices match expected tokens for unambiguous entities.
    by_label = {label: text[start:end] for start, end, label in spans}
    assert by_label["EMAIL"] == "a.mueller@example-hospital.de"
    assert by_label["PHONE"] == "+49 171 1234567"
    assert by_label["IPV4"] == "192.168.14.2"
    assert by_label["IBAN"] == "DE89 3704 0044 0532 0130 00"
    assert "KUNDE-884213" in by_label["ACCOUNT"]
    assert "Berliner Str." in by_label["ADDRESS"]


def test_eval_case_pii_contact() -> None:
    body = (
        "Hello, please update the email on my account from a.mueller@example-hospital.de "
        "to anna.mueller@example-hospital.de. My phone is +49 171 5558842, "
        "account KUNDE-884213, and our office IP range starts at 192.168.14.2."
    )
    _, masked, counts = _assert_span_invariants(body)

    assert counts == {"EMAIL": 2, "PHONE": 1, "ACCOUNT": 1, "IPV4": 1}
    for secret in (
        "a.mueller@example-hospital.de",
        "anna.mueller@example-hospital.de",
        "5558842",
        "KUNDE-884213",
        "192.168.14.2",
    ):
        assert secret not in masked


def test_eval_case_guard_pii_masking_en() -> None:
    body = (
        "Hello support team, could you please update the billing profile on account ACCT-904821? "
        "Our primary contact email is claire.bennett@northstar-clinic.org, phone +1 617-555-0194, "
        "office allowlist IP 10.42.18.75, and updated direct-debit IBAN DE89 3704 0044 0532 0130 00. "
        "Thank you."
    )
    _, masked, counts = _assert_span_invariants(body)

    assert counts == {"ACCOUNT": 1, "EMAIL": 1, "PHONE": 1, "IPV4": 1, "IBAN": 1}
    assert "Thank you." in masked
    for secret in (
        "ACCT-904821",
        "claire.bennett@northstar-clinic.org",
        "555-0194",
        "10.42.18.75",
        "DE89",
        "0130",
    ):
        assert secret not in masked
