"""Mask personal data before ticket text leaves the machine for a cloud LLM (B3).

Owner: B3 / Guardrails (PII and "What the AI saw"). Called by ``sentinel/pipeline.py``
before prompt construction: the operator console still shows the original ticket and
retrieval runs on the original text, while the cloud LLM sees deterministic placeholders
(``<EMAIL>``, ``<IBAN>``, ``<PHONE>``, ...).

Contracts (keep stable):
    mask_spans(text: str) -> list[tuple[int, int, str]]
        Sorted, non-overlapping ``(start, end, label)`` character offsets in ``text``.
    mask_pii(text: str) -> tuple[str, dict[str, int]]
        Built directly on ``mask_spans(text)``: replaces each span with ``f"<{label}>"``
        and returns ``(masked_text, {label: count})`` matching ``mask_spans`` 1-to-1.
    has_pii(text: str) -> bool
        Returns ``True`` iff ``text`` contains at least one detected PII span.
    PATTERNS: list[tuple[str, re.Pattern[str]]]
        Exported regex list in priority order for inspection / compatibility.
"""

from __future__ import annotations

import re

# Deterministic overlap resolution priority (lower index wins; longer span wins on tie).
_LABEL_PRIORITY: dict[str, int] = {
    "EMAIL": 0,
    "URL": 1,
    "IBAN": 2,
    "IPV4": 3,
    "CARD": 4,
    "PHONE": 5,
    "ACCOUNT": 6,
    "ADDRESS": 7,
}

# ISO 13616 / SEPA IBAN lengths by two-letter country code.
_IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22,
    "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DK": 18,
    "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27, "GB": 22,
    "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22,
    "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28,
    "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "LY": 25, "MC": 27, "MD": 24,
    "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15, "PK": 24,
    "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SC": 31,
    "SE": 24, "SI": 19, "SK": 24, "SM": 27, "ST": 25, "SV": 28, "TL": 23, "TN": 24,
    "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}

_URL_TRAILING_PUNCT = ".,;:!?)]}>\"'"

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,}"
    r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9])"
)

_URL_RE = re.compile(r"(?<![A-Za-z0-9])https?://\S+", re.IGNORECASE)

_IBAN_HEAD_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2})(\d{2})")
_IBAN_EXPORT_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]{4}){2,7}(?:[ -]?[A-Z0-9]{1,4})?(?![A-Za-z0-9])"
)

_IPV4_RE = re.compile(
    r"(?<![A-Za-z0-9.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![A-Za-z0-9]|\.\d)"
)
_VERSION_PREFIX_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])"
    r"(?:v|ver|version|build|release|sdk|app|ios|macos|windows|python|node)"
    r"(?:\.[ \t]*|[ \t]*[:=-][ \t]*|[ \t]+(?:v\.?[ \t]*)?)$",
    re.IGNORECASE,
)

# Card patterns: 4-group formatted, Amex 4-6-5 formatted, or compact 13-19 digits.
_CARD_RE = re.compile(
    r"(?<![A-Za-z0-9.-])"
    r"(?:"
    r"\d{4}(?:[ -]\d{4}){2}[ -]\d{1,4}(?:[ -]\d{1,3})?"
    r"|\d{4}[ -]\d{6}[ -]\d{5}"
    r"|\d{13,19}"
    r")"
    r"(?![A-Za-z0-9-]|\.\d)"
)
_IBAN_PREFIX_RE = re.compile(r"(?:^|[^A-Za-z0-9])[A-Z]{2}\d{2}[ -]$")

# Phone patterns: international (+ / 00), parenthesized area code, DE/EU trunk-0, NANP 3-3-4.
_PHONE_INTL_RE = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"(?:"
    r"\+[1-9]\d{0,2}(?:[ \t-]*\(0\)[ \t-]*|[ \t-]*\(\d{1,5}\)[ \t-]*|[ \t-]+|(?=\d{6,14}(?![A-Za-z0-9])))\d{1,12}"
    r"|00[1-9]\d{0,2}(?:[ \t-]*\(0\)[ \t-]*|[ \t-]*\([1-9]\d{0,4}\)[ \t-]*|[ \t-]+)[1-9]\d{0,11}"
    r")"
    r"(?:[ \t]*/[ \t]*\d{1,8})?(?:[ \t-]+\d{1,8}){0,4}"
    r"(?![A-Za-z0-9]|\.\d)"
)
_PHONE_PAREN_RE = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"\(\d{2,5}\)[ \t-]*"
    r"\d{2,9}(?:[ \t-]+\d{1,5}){0,3}"
    r"(?![A-Za-z0-9]|\.\d)"
)
_PHONE_TRUNK0_RE = re.compile(
    r"(?<![A-Za-z0-9.-])"
    r"0[1-9]\d{1,4}(?:[ \t]*/[ \t]*|[ \t-]+)"
    r"[1-9]\d{1,8}(?:[ \t-]+\d{1,5}){0,3}"
    r"(?![A-Za-z0-9]|\.\d)"
)
_PHONE_NANP_RE = re.compile(
    r"(?<![A-Za-z0-9.-])"
    r"[2-9]\d{2}[ -]\d{3}[ -]\d{4}"
    r"(?![A-Za-z0-9]|\.\d)"
)
_PHONE_EXPORT_RE = re.compile(
    f"(?:{_PHONE_INTL_RE.pattern})|(?:{_PHONE_PAREN_RE.pattern})|"
    f"(?:{_PHONE_TRUNK0_RE.pattern})|(?:{_PHONE_NANP_RE.pattern})"
)

_DATE_LIKE_RE = re.compile(
    r"^(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})$"
)

_ACCOUNT_PREFIXED_RE = re.compile(
    r"\b(?:"
    r"(?:acct|konto-nr|kunden-nr)\.[ \t#:=–-]{0,3}"
    r"|(?:acct|konto-nr|kunden-nr|account|konto|kontonummer|kundennummer|customer)"
    r"(?:[ \t]+(?:no\.?|nr\.?|num(?:ber)?|id))?"
    r"[ \t#:=–-]{1,4}"
    r")"
    r"([A-Za-z0-9][A-Za-z0-9-]{3,}[A-Za-z0-9])"
    r"(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
_ACCOUNT_STANDALONE_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:KUNDE|ACCT)-\d{4,}(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
_ACCOUNT_UNIT_SUFFIX_RE = re.compile(
    r"^\d+-(?:day|days|hour|hours|hr|hrs|min|mins|month|months|week|weeks|year|years|yr|yrs|"
    r"eur|euro|usd|gbp|chf|gb|mb|tb|kb|ms|sec)$",
    re.IGNORECASE,
)
_ACCOUNT_EXPORT_RE = re.compile(
    f"(?:{_ACCOUNT_PREFIXED_RE.pattern})|(?:{_ACCOUNT_STANDALONE_RE.pattern})",
    re.IGNORECASE,
)

# German street addresses: compound stem+suffix OR 1-2 capitalized words + standalone suffix.
_DE_SUFFIX = r"(?i:straße|strasse|str\.|weg|platz|allee|gasse|ring|damm|ufer|chaussee)"
_DE_POSTAL_CITY = (
    r"(?:,?[ \t]+\d{5}[ \t]+(?:(?:Bad|Sankt|St\.)[ \t]+)?[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+"
    r"(?:[ \t]+(?:am|an|im|in|ob|vor)[ \t]+(?:der[ \t]+|dem[ \t]+)?[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+)?)?"
)
_DE_HOUSE_NUM = r"\d{1,4}[A-Za-z]?(?:-\d{1,4}[A-Za-z]?)?"
_ADDR_DE_COMPOUND_RE = re.compile(
    rf"(?<![A-Za-zÄÖÜäöüß0-9-])"
    rf"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{{1,}}{_DE_SUFFIX}"
    rf"[ \t]+{_DE_HOUSE_NUM}{_DE_POSTAL_CITY}"
    rf"(?![A-Za-zÄÖÜäöüß0-9])"
)
_ADDR_DE_SPACED_RE = re.compile(
    rf"(?<![A-Za-zÄÖÜäöüß0-9-])"
    rf"((?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]*[ \t]+){{1,2}}){_DE_SUFFIX}"
    rf"[ \t]+{_DE_HOUSE_NUM}{_DE_POSTAL_CITY}"
    rf"(?![A-Za-zÄÖÜäöüß0-9])"
)
_DE_ADDR_STOPWORDS: frozenset[str] = frozenset({
    "the", "my", "our", "your", "at", "on", "in", "to", "for", "from", "with", "by", "of",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "auf", "bei", "beim", "zum", "zur", "nach", "über", "von", "vom", "mit", "und", "oder",
    "bitte", "please", "see", "call", "send", "visit", "im", "am", "an",
})

# English street addresses: house number + 1-3 capitalized words + street type + optional unit.
_EN_STREET_WORD = r"(?:(?:N|S|E|W|NE|NW|SE|SW)\.?|\d{1,3}(?:st|nd|rd|th)|St\.|[A-Z][A-Za-z'-]+)"
_EN_STREET_TYPE = (
    r"(?:Street|Avenue|Road|Boulevard|Drive|Lane|Way|Court|Place|Parkway|"
    r"(?:St|Ave|Rd|Blvd|Dr|Ln|Ct|Pl|Pkwy)\.?)"
)
_EN_UNIT = r"(?:,?[ \t]+(?:(?i:apt|suite|ste|unit)\.?[ \t]*#?[ \t]*|#)[A-Za-z0-9-]+)?"
_ADDR_EN_RE = re.compile(
    rf"(?<![A-Za-z0-9.-])"
    rf"\d{{1,5}}[A-Za-z]?[ \t]+"
    rf"(?:{_EN_STREET_WORD}[ \t]+){{1,3}}"
    rf"{_EN_STREET_TYPE}"
    rf"{_EN_UNIT}"
    rf"(?![A-Za-z0-9])"
)
_ADDRESS_EXPORT_RE = re.compile(
    f"(?:{_ADDR_DE_COMPOUND_RE.pattern})|(?:{_ADDR_DE_SPACED_RE.pattern})|(?:{_ADDR_EN_RE.pattern})"
)

# Exported for inspection / compatibility, ordered by overlap resolution priority.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", _EMAIL_RE),
    ("URL", _URL_RE),
    ("IBAN", _IBAN_EXPORT_RE),
    ("IPV4", _IPV4_RE),
    ("CARD", _CARD_RE),
    ("PHONE", _PHONE_EXPORT_RE),
    ("ACCOUNT", _ACCOUNT_EXPORT_RE),
    ("ADDRESS", _ADDRESS_EXPORT_RE),
]


def _luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _is_compact_timestamp(digits: str) -> bool:
    if len(digits) != 14 or not digits.startswith(("19", "20")):
        return False
    month = int(digits[4:6])
    day = int(digits[6:8])
    hour = int(digits[8:10])
    minute = int(digits[10:12])
    second = int(digits[12:14])
    return 1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59


def _find_emails(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), "EMAIL") for m in _EMAIL_RE.finditer(text)]


def _find_urls(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for m in _URL_RE.finditer(text):
        raw = m.group(0)
        trimmed = raw.rstrip(_URL_TRAILING_PUNCT)
        scheme_end = trimmed.find("://") + 3
        if len(trimmed) > scheme_end:
            spans.append((m.start(), m.start() + len(trimmed), "URL"))
    return spans


def _find_ibans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    n = len(text)
    for m in _IBAN_HEAD_RE.finditer(text):
        country = m.group(1)
        expected = _IBAN_LENGTHS.get(country)
        if expected is None:
            continue
        compact = list(m.group(0))
        pos = m.end()
        while len(compact) < expected and pos < n:
            ch = text[pos]
            if ch in (" ", "-"):
                if pos + 1 < n and ("A" <= text[pos + 1] <= "Z" or "0" <= text[pos + 1] <= "9"):
                    pos += 1
                    continue
                break
            if "A" <= ch <= "Z" or "0" <= ch <= "9":
                compact.append(ch)
                pos += 1
            else:
                break
        if len(compact) != expected:
            continue
        if pos < n and text[pos].isalnum():
            continue
        bban = "".join(compact[4:])
        if country == "DE":
            if not bban.isdigit():
                continue
        else:
            digit_count = sum(c.isdigit() for c in bban)
            if digit_count < 6 or digit_count * 2 < len(bban):
                continue
        spans.append((m.start(), pos, "IBAN"))
    return spans


def _find_ipv4s(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for m in _IPV4_RE.finditer(text):
        octets = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        if any(o > 255 for o in octets):
            continue
        prefix = text[max(0, m.start() - 32) : m.start()]
        if _VERSION_PREFIX_RE.search(prefix):
            continue
        spans.append((m.start(), m.end(), "IPV4"))
    return spans


def _find_cards(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for m in _CARD_RE.finditer(text):
        raw = m.group(0)
        if _DATE_LIKE_RE.match(raw):
            continue
        if _IBAN_PREFIX_RE.search(text[max(0, m.start() - 6) : m.start()]):
            continue
        digits = "".join(c for c in raw if c.isdigit())
        if not (13 <= len(digits) <= 19):
            continue
        has_space = " " in raw
        has_dash = "-" in raw
        if has_space and has_dash:
            continue
        if has_space or has_dash:
            spans.append((m.start(), m.end(), "CARD"))
        elif _luhn_valid(digits) and not _is_compact_timestamp(digits):
            spans.append((m.start(), m.end(), "CARD"))
    return spans


def _find_phones(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for pattern in (_PHONE_INTL_RE, _PHONE_PAREN_RE, _PHONE_TRUNK0_RE, _PHONE_NANP_RE):
        for m in pattern.finditer(text):
            raw = m.group(0)
            if _DATE_LIKE_RE.match(raw):
                continue
            digit_count = sum(c.isdigit() for c in raw)
            if 7 <= digit_count <= 15:
                spans.append((m.start(), m.end(), "PHONE"))
    return spans


def _find_accounts(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for m in _ACCOUNT_PREFIXED_RE.finditer(text):
        ident = m.group(1)
        if _DATE_LIKE_RE.match(ident) or _ACCOUNT_UNIT_SUFFIX_RE.match(ident):
            continue
        digit_count = sum(c.isdigit() for c in ident)
        if digit_count == 0:
            continue
        if ident != ident.upper() and digit_count < 4:
            continue
        spans.append((m.start(), m.end(), "ACCOUNT"))
    for m in _ACCOUNT_STANDALONE_RE.finditer(text):
        spans.append((m.start(), m.end(), "ACCOUNT"))
    return spans


def _find_addresses(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for m in _ADDR_DE_COMPOUND_RE.finditer(text):
        spans.append((m.start(), m.end(), "ADDRESS"))
    for m in _ADDR_DE_SPACED_RE.finditer(text):
        lead = m.group(1)
        tokens = lead.split()
        drop = 0
        while drop < len(tokens) and tokens[drop].lower() in _DE_ADDR_STOPWORDS:
            drop += 1
        if drop == len(tokens):
            continue
        start = m.start()
        if drop > 0:
            # Advance start past dropped leading stopword tokens.
            offset = 0
            for idx in range(drop):
                pos = lead.find(tokens[idx], offset)
                offset = pos + len(tokens[idx])
            while offset < len(lead) and lead[offset] in (" ", "\t"):
                offset += 1
            start += offset
        spans.append((start, m.end(), "ADDRESS"))
    for m in _ADDR_EN_RE.finditer(text):
        end = m.end()
        # Do not swallow a sentence-ending period after abbreviated suffixes (e.g. "Ave. Thanks.").
        if text[end - 1] == "." and re.match(r"^[ \t\n]+[A-Z]", text[end:]):
            end -= 1
        spans.append((m.start(), end, "ADDRESS"))
    return spans


def _resolve_overlaps(candidates: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Select non-overlapping spans by label priority, breaking ties by longer span."""
    ordered = sorted(
        candidates,
        key=lambda s: (_LABEL_PRIORITY.get(s[2], 99), -(s[1] - s[0]), s[0]),
    )
    accepted: list[tuple[int, int, str]] = []
    for start, end, label in ordered:
        if any(start < a_end and a_start < end for a_start, a_end, _ in accepted):
            continue
        accepted.append((start, end, label))
    accepted.sort(key=lambda s: (s[0], s[1]))
    return accepted


def mask_spans(text: str) -> list[tuple[int, int, str]]:
    """Return sorted, non-overlapping ``(start, end, label)`` PII spans in ``text``."""
    if not text:
        return []
    candidates: list[tuple[int, int, str]] = []
    candidates.extend(_find_emails(text))
    candidates.extend(_find_urls(text))
    candidates.extend(_find_ibans(text))
    candidates.extend(_find_ipv4s(text))
    candidates.extend(_find_cards(text))
    candidates.extend(_find_phones(text))
    candidates.extend(_find_accounts(text))
    candidates.extend(_find_addresses(text))
    return _resolve_overlaps(candidates)


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """Return ``(masked_text, {label: count})``. Counts are what the UI badge shows."""
    if not text:
        return "", {}
    spans = mask_spans(text)
    if not spans:
        return text, {}
    parts: list[str] = []
    counts: dict[str, int] = {}
    cursor = 0
    for start, end, label in spans:
        parts.append(text[cursor:start])
        parts.append(f"<{label}>")
        counts[label] = counts.get(label, 0) + 1
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), counts


def has_pii(text: str) -> bool:
    """Return ``True`` iff ``text`` contains any detected PII span."""
    return bool(mask_spans(text))
