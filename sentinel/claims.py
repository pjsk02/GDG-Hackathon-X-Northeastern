"""Number-and-promise guard on drafted replies (N4).

Owner: D (Sujitha). Called by ``sentinel/pipeline.py`` after citation verification;
every finding escalates the ticket to review with reason
``"R6 unbacked <kind> in draft: '<text>'"``.

Contract (keep stable):
    check_claims(reply: str, verified: list[VerifiedCitation]) -> list[GuardFinding]

Rule: every amount of money, percentage, date/duration, standalone number, and
promise phrase (EN and DE) in ``reply`` must appear in at least one verified
citation quote (normalized, boundary-aware). Ticket IDs (``TKT-01234``) and PII
placeholders (``<EMAIL>``, ``<IPV4>``) are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.contracts import GuardFinding, GuardKind, VerifiedCitation

_UNBACKED_REASON = "not found in any verified quote"

# Horizontal whitespace only (including NBSP and narrow NBSP) so multi-token
# spans do not accidentally bridge across newlines.
_HS = r"[ \t\u00a0\u202f]"
_DASH = r"[-\u2010-\u2015\u2212]"
_APOS = r"['\u2019]"
_NUM = r"\d+(?:[.,]\d+)*"

# Tokens that must never be treated as numeric claims (and must never back them).
_IGNORE_RE = re.compile(r"(?i:\bTKT-\d+\b)|<[A-Z0-9_]+>")

# 1. Money (EN / DE): symbol or currency code/name before or after a number.
_CURRENCY_SYM = r"[€$£]"
_CURRENCY_WORD = r"(?:CHF|EUR|USD|GBP|Euros?|Dollars?)"
_MONEY_RE = re.compile(
    rf"{_CURRENCY_SYM}{_HS}*{_NUM}\b"
    rf"|\b{_CURRENCY_WORD}{_HS}*{_NUM}\b"
    rf"|\b{_NUM}{_HS}*{_CURRENCY_SYM}"
    rf"|\b{_NUM}{_HS}*{_CURRENCY_WORD}\b",
    re.IGNORECASE,
)

# 2. Percent (EN / DE).
_PERCENT_RE = re.compile(
    rf"\b{_NUM}(?:{_HS}*%|{_HS}*(?:per{_HS}?cent|prozent)\b)",
    re.IGNORECASE,
)

# 3. Dates, weekday deadlines, and durations (EN / DE).
_MONTH_FULL = (
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Januar|Jänner|Jaenner|Februar|März|Maerz|Mai|Juni|Juli|Oktober|Dezember"
)
_MONTH_ABBR = r"(?:Jan|Feb|Mar|Mrz|Apr|Jun|Jul|Aug|Sept?|Oct|Okt|Nov|Dec|Dez)\.?"
_MONTH = rf"(?:{_MONTH_FULL}|{_MONTH_ABBR})"
_DAY = r"(?:0?[1-9]|[12]\d|3[01])"

_EN_WEEKDAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
_DE_WEEKDAY = r"(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)"

_EN_WORD_NUM = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|fourteen|fifteen|twenty|thirty)"
)
_DE_WORD_NUM = (
    r"(?:ein(?:e[mnr]?)?|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn"
    r"|elf|zwölf|zwoelf|vierzehn|fünfzehn|fuenfzehn|zwanzig|dreißig|dreissig)"
)

_NUM_RANGE = rf"\d+(?:[.,]\d+)?(?:{_HS}*(?:{_DASH}|to|bis){_HS}*\d+(?:[.,]\d+)?)?"
_WORD_RANGE = (
    rf"(?:{_EN_WORD_NUM}(?:{_HS}*(?:{_DASH}|to){_HS}*{_EN_WORD_NUM})?"
    rf"|{_DE_WORD_NUM}(?:{_HS}*(?:{_DASH}|bis){_HS}*{_DE_WORD_NUM})?)"
)

_DURATION_PREP = rf"(?:within|in|for|after|innerhalb{_HS}+von|innerhalb|binnen)"

_DURATION_LONG_UNIT = (
    r"(?:seconds?|minutes?|hours?"
    rf"|(?:(?:business|working|calendar){_HS}+)?days?"
    r"|weeks?|months?|years?"
    r"|Sekunden?|Minuten?|Stunden?"
    r"|(?:Werk|Arbeits|Kalender)?Tagen?"
    r"|Wochen?|Monat(?:e|en)?|Jahr(?:e|en)?)"
)
_DURATION_COMPACT_UNIT = r"(?:h|hrs?\.?|mins?\.?|secs?\.?|Std\.?|Min\.?|Sek\.?)"

_DATE_RE = re.compile(
    # ISO dates: 2026-11-21
    r"\b\d{4}-\d{2}-\d{2}\b"
    # Dot numeric dates: 21.11.2026, 21.11.26 (avoid IPv4 fragments)
    rf"|(?<!\d\.)\b{_DAY}\.(?:0?[1-9]|1[0-2])\.(?:\d{{4}}|\d{{2}})\b(?!\.\d)"
    # Slash numeric dates: 11/21/2026, 21/11/2026
    rf"|(?<!\d/)\b{_DAY}/{_DAY}/(?:\d{{4}}|\d{{2}})\b(?!/\d)"
    # Named month dates (day first): 15 March 2026, 15. März, 15. Mai 2026
    rf"|\b{_DAY}(?:\.|st|nd|rd|th)?(?:{_HS}+of)?{_HS}+{_MONTH}(?!\w)(?:{_HS}*,?{_HS}+\d{{4}}\b)?"
    # Named month dates (month first): March 15, March 15, 2026, May 2026
    rf"|\b{_MONTH}(?!\w){_HS}+(?:{_DAY}(?:st|nd|rd|th)?(?:{_HS}*,?{_HS}+\d{{4}})?|\d{{4}})\b"
    # Weekday deadlines (EN / DE): by Friday, before Monday, until Tuesday, bis Freitag, am Montag, vor Mittwoch
    rf"|\b(?:(?:by|before|until|on)(?:{_HS}+(?:this|next))?|this|next){_HS}+{_EN_WEEKDAY}\b"
    rf"|\b(?:(?:bis(?:{_HS}+zum)?|am|vor|ab)(?:{_HS}+(?:nächsten|naechsten|kommenden))?|nächsten|naechsten|kommenden){_HS}+{_DE_WEEKDAY}\b"
    # Numeric durations with optional leading preposition and optional range:
    # 2-3 days, 2 to 3 business days, 24 hours, 48 Stunden, within 2 days,
    # innerhalb von 48 Stunden, 24h, 48 Std., 3 Werktagen
    rf"|\b(?:{_DURATION_PREP}{_HS}+)?{_NUM_RANGE}(?:{_HS}+{_DURATION_LONG_UNIT}\b|{_HS}*{_DURATION_COMPACT_UNIT}(?!\w))"
    # Written-word durations (EN / DE): within two days, two business days, zwei Tagen, drei Werktagen
    rf"|\b(?:{_DURATION_PREP}{_HS}+)?{_WORD_RANGE}{_HS}+{_DURATION_LONG_UNIT}\b",
    re.IGNORECASE,
)

_DURATION_PREP_PREFIX_RE = re.compile(
    rf"^(?:within|in|for|after|innerhalb{_HS}+von|innerhalb|binnen){_HS}+",
    re.IGNORECASE,
)

# 4. Remaining standalone numbers.
_NUMBER_RE = re.compile(rf"\b{_NUM}\b")

# 5. Promises / guarantees / refunds / freebies (EN and DE), checked independently.
_PROMISE_PATTERNS: tuple[str, ...] = (
    # EN
    rf"\bwe{_HS}+guarantee\b",
    rf"\b(?:uptime|sla){_HS}+guarantee\b",
    rf"\bguaranteed(?:{_HS}+(?:uptime|refund|delivery|resolution|fix))?\b",
    rf"\b(?:full|partial){_HS}+refund\b",
    rf"\bmoney(?:{_DASH}|{_HS})back\b",
    rf"\bwe(?:{_APOS}ll|{_HS}+(?:will|can)){_HS}+refund\b",
    rf"\b(?:issue|process){_HS}+(?:a|your|the){_HS}+refund\b",
    rf"\bfree{_HS}+of{_HS}+charge\b",
    rf"\bat{_HS}+no(?:{_HS}+(?:extra|additional))?{_HS}+(?:cost|charge)\b",
    rf"\b(?:financial|full|unlimited){_HS}+compensation\b",
    rf"\bwe(?:{_APOS}ll|{_HS}+(?:will|can)){_HS}+waive(?:{_HS}+(?:the|all|any|your){_HS}+fees?)?\b",
    rf"\bwe(?:{_APOS}ll|{_HS}+(?:will|can)){_HS}+(?:credit|reimburse|compensate)\b",
    rf"\bwaive{_HS}+(?:the|all|any|your){_HS}+fees?\b",
    rf"\bwe{_HS}+promise\b",
    rf"\bwe{_HS}+assure{_HS}+you\b",
    rf"\bzero{_HS}+downtime\b",
    rf"\bconfirm(?:{_HS}+the)?{_HS}+cancellation{_HS}+of{_HS}+your{_HS}+contract\b",
    rf"\bcancel{_HS}+your{_HS}+contract\b",
    # DE (supports umlaut and ae/oe/ue ASCII spellings)
    rf"\bwir{_HS}+garantieren\b",
    rf"\bgarantiert(?:e[nrs]?)?(?:{_HS}+(?:verf(?:ü|ue)gbarkeit|(?:r(?:ü|ue)ck)?erstattung|l(?:ö|oe)sung))?\b",
    r"\bverf(?:ü|ue)gbarkeitsgarantie\b",
    rf"\bsla(?:{_DASH}|{_HS})?garantie\b",
    rf"\bwir{_HS}+erstatten\b",
    rf"\b(?:vollst(?:ä|ae)ndige[nr]?|volle[nr]?){_HS}+(?:r(?:ü|ue)ck)?erstattung\b",
    r"\bkostenlos(?:e[mnrs]?)?\b",
    r"\bkostenfrei(?:e[mnrs]?)?\b",
    r"\bunentgeltlich(?:e[mnrs]?)?\b",
    rf"\bohne(?:{_HS}+(?:zus(?:ä|ae)tzliche|weitere))?{_HS}+kosten\b",
    rf"\bwir{_HS}+schreiben(?:[^.!?;:,\n]{{0,60}}?)?{_HS}+gut\b",
    rf"\bgutschrift{_HS}+wird(?:{_HS}+(?:umgehend|sofort|automatisch|zeitnah))?{_HS}+(?:erstellt|genehmigt|best(?:ä|ae)tigt)\b",
    rf"\bwir{_HS}+entsch(?:ä|ae)digen\b",
    rf"\bentsch(?:ä|ae)digung{_HS}+wird(?:{_HS}+(?:umgehend|sofort|automatisch|zeitnah))?{_HS}+(?:gezahlt|gew(?:ä|ae)hrt|ausgezahlt)\b",
    rf"\bwir{_HS}+versprechen\b",
    rf"\bwir{_HS}+sichern(?:[^.!?;:,\n]{{0,60}}?)?{_HS}+zu\b",
)
_PROMISE_RE = re.compile("|".join(_PROMISE_PATTERNS), re.IGNORECASE)

_MONEY_PREFIX_SPLIT_RE = re.compile(
    r"^([€$£]|chf|eur|usd|gbp|euros?|dollars?)\s*(\d[\d.,]*)$"
)
_MONEY_SUFFIX_SPLIT_RE = re.compile(
    r"^(\d[\d.,]*)\s*([€$£]|chf|eur|usd|gbp|euros?|dollars?)$"
)
_PERCENT_SPLIT_RE = re.compile(r"^(\d[\d.,]*)\s*(%|per\s?cent|prozent)$")

_NORM_TRANS = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u2033": '"',
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
})


@dataclass(frozen=True)
class _Claim:
    start: int
    end: int
    kind: GuardKind
    text: str


def _mask_spans(text: str, pattern: re.Pattern[str]) -> str:
    """Replace every regex match with equal-length spaces to preserve offsets."""
    return pattern.sub(lambda m: " " * (m.end() - m.start()), text)


def _extract_and_mask(
    original: str,
    masked: str,
    pattern: re.Pattern[str],
    kind: GuardKind,
) -> tuple[list[_Claim], str]:
    """Extract claims from ``masked`` (preserving exact slices from ``original``) and blank them."""
    claims: list[_Claim] = []
    chars = list(masked)
    for match in pattern.finditer(masked):
        start, end = match.span()
        claims.append(_Claim(start=start, end=end, kind=kind, text=original[start:end]))
        chars[start:end] = [" "] * (end - start)
    return claims, "".join(chars)


def _extract_claims(reply: str) -> list[_Claim]:
    """Extract all claims from ``reply`` in appearance order."""
    base_masked = _mask_spans(reply, _IGNORE_RE)
    working = base_masked
    claims: list[_Claim] = []

    for pattern, kind in (
        (_MONEY_RE, "money"),
        (_PERCENT_RE, "percent"),
        (_DATE_RE, "date"),
        (_NUMBER_RE, "number"),
    ):
        found, working = _extract_and_mask(reply, working, pattern, kind)
        claims.extend(found)

    # Promises are checked independently so e.g. "we guarantee 99.9% uptime"
    # catches both the promise and the percentage.
    for match in _PROMISE_RE.finditer(base_masked):
        start, end = match.span()
        claims.append(_Claim(start=start, end=end, kind="promise", text=reply[start:end]))

    claims.sort(key=lambda c: (c.start, c.end))
    return claims


def _normalize(text: str) -> str:
    """Lowercase, normalize curly quotes/dashes, and collapse whitespace."""
    cleaned = text.translate(_NORM_TRANS).lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_quote(quote: str) -> str:
    """Mask ignored tokens in a quote and normalize for claim lookup."""
    return _normalize(_mask_spans(quote, _IGNORE_RE))


def _dedup_key(kind: GuardKind, normalized: str) -> tuple[GuardKind, str]:
    """Build a canonical deduplication key for a finding."""
    if kind == "money":
        if m := _MONEY_PREFIX_SPLIT_RE.match(normalized):
            return (kind, f"{m.group(1)}{m.group(2)}")
        if m := _MONEY_SUFFIX_SPLIT_RE.match(normalized):
            return (kind, f"{m.group(1)}{m.group(2)}")
    elif kind == "percent":
        if m := _PERCENT_SPLIT_RE.match(normalized):
            return (kind, f"{m.group(1)}{m.group(2)}")
    return (kind, normalized)


def _build_match_pattern(kind: GuardKind, normalized: str) -> re.Pattern[str]:
    """Compile a boundary-aware regex for matching ``normalized`` inside a quote."""
    if kind == "money":
        if m := _MONEY_PREFIX_SPLIT_RE.match(normalized):
            body = rf"{re.escape(m.group(1))}\s*{re.escape(m.group(2))}"
        elif m := _MONEY_SUFFIX_SPLIT_RE.match(normalized):
            body = rf"{re.escape(m.group(1))}\s*{re.escape(m.group(2))}"
        else:
            body = re.escape(normalized)
    elif kind == "percent":
        if m := _PERCENT_SPLIT_RE.match(normalized):
            body = rf"{re.escape(m.group(1))}\s*{re.escape(m.group(2))}"
        else:
            body = re.escape(normalized)
    elif kind == "date":
        escaped = re.escape(normalized)
        body = re.sub(r"(?<=\d)(?:\\ )?\\-(?:\\ )?(?=\d)", r"\\s*-\\s*", escaped)
        body = re.sub(
            r"(?<=\d)(?:\\ )?(?=(?:h|hrs?\.?|mins?\.?|secs?\.?|std\.?|sek\.?)$)",
            r"\\s*",
            body,
        )
    else:
        body = re.escape(normalized)

    prefix = ""
    if normalized[0].isdigit():
        prefix = r"(?<!\w)(?<!\d[.,])"
    elif normalized[0].isalnum() or normalized[0] == "_":
        prefix = r"(?<!\w)"

    suffix = ""
    if normalized[-1].isdigit():
        suffix = r"(?!\w)(?![.,]\d)"
    elif normalized[-1].isalnum() or normalized[-1] == "_":
        suffix = r"(?!\w)"

    return re.compile(f"{prefix}{body}{suffix}")


def _is_backed(kind: GuardKind, normalized: str, normalized_quotes: list[str]) -> bool:
    """Return True if ``normalized`` is backed by at least one verified quote."""
    if not normalized_quotes:
        return False

    candidates = [normalized]
    if kind == "date":
        stripped = _DURATION_PREP_PREFIX_RE.sub("", normalized).strip()
        if stripped and stripped != normalized:
            candidates.append(stripped)

    for candidate in candidates:
        pattern = _build_match_pattern(kind, candidate)
        if any(pattern.search(quote) for quote in normalized_quotes):
            return True
    return False


def check_claims(reply: str, verified: list[VerifiedCitation]) -> list[GuardFinding]:
    """Return unbacked numeric, temporal, or promise claims found in ``reply``."""
    if not reply or not reply.strip():
        return []

    normalized_quotes = [
        q for v in verified if (q := _normalize_quote(v.evidence_quote))
    ]

    findings: list[GuardFinding] = []
    seen: set[tuple[GuardKind, str]] = set()

    for claim in _extract_claims(reply):
        normalized = _normalize(claim.text)
        if not normalized:
            continue
        if _is_backed(claim.kind, normalized, normalized_quotes):
            continue
        key = _dedup_key(claim.kind, normalized)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            GuardFinding(
                kind=claim.kind,
                text=claim.text,
                reason=_UNBACKED_REASON,
            )
        )

    return findings
