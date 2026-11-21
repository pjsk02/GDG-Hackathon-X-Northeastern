"""Mask personal data before ticket text leaves the machine for a cloud LLM.

Deterministic regexes, applied to the *prompt only*: the operator console still shows the
original ticket, and retrieval runs on the original text (masking it would hurt matching).
Placeholders keep the shape of the original (<EMAIL>, <IBAN>) so the model can still write
"we have sent the details to your email address" without ever seeing it.
"""

from __future__ import annotations

import re

# Order matters: IBAN and card before the generic long-number rule, IP before phone.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")),
    ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[ ]?(?:[A-Z0-9]{4}[ ]?){2,7}[A-Z0-9]{1,4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\d\b")),
    # +49 171 1234567 / (617) 555-0134 / 0171-1234567
    ("PHONE", re.compile(r"(?<![\w.])(?:\+\d{1,3}[ -]?)?(?:\(\d{2,4}\)[ -]?|\d{2,4}[ -])\d{3,4}[ -]?\d{3,5}(?![\w.])")),
    ("ACCOUNT", re.compile(r"\b(?:acct|account|konto|kundennummer|customer)[ #:-]{1,3}([A-Z0-9-]{6,})\b", re.I)),
    ("URL", re.compile(r"\bhttps?://\S+")),
]


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """Return (masked_text, {label: count}). Counts are what the UI badge shows."""
    found: dict[str, int] = {}
    if not text:
        return "", found
    masked = text
    for label, pattern in PATTERNS:
        masked, n = pattern.subn(f"<{label}>", masked)
        if n:
            found[label] = found.get(label, 0) + n
    return masked, found


def has_pii(text: str) -> bool:
    return bool(mask_pii(text)[1])
