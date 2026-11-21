"""Prompt-injection detector, gate rule R7 (N9).

Owner: D (Sujitha). Called by ``sentinel/pipeline.py`` during the pre-draft gate;
every label returned escalates the ticket with reason
``"R7 prompt injection: <hit>"``.

Contract (keep stable):
    detect_injection(text: str) -> list[str]
    -> deduplicated list of short English labels describing matched injection
       patterns (e.g. ``["asks to ignore previous instructions"]``), or ``[]``
       when clean or empty.

Detects English and German prompt injections across five categories:
1. Instruction override (``"asks to ignore previous instructions"``)
2. Role / persona hijacking & jailbreak (``"attempts role or jailbreak override"``)
3. Policy spoofing (``"attempts to spoof company policy"``)
4. System prompt extraction (``"requests hidden system prompt"``)
5. Delimiter / role-tag / JSON-output tampering
   (``"embeds fake system delimiter or output override"``)
"""

from __future__ import annotations

import re
import unicodedata

LABEL_OVERRIDE = "asks to ignore previous instructions"
LABEL_JAILBREAK = "attempts role or jailbreak override"
LABEL_POLICY_SPOOF = "attempts to spoof company policy"
LABEL_PROMPT_LEAK = "requests hidden system prompt"
LABEL_DELIMITER = "embeds fake system delimiter or output override"

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_DASH_RE = re.compile(r"[\u2010-\u2015\u2212]")
_HORIZ_WS_RE = re.compile(r"[ \t\f\v]+")

_UMLAUT_TABLE = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


def _normalize(text: str) -> str:
    """Fold case, Unicode width, umlauts/eszett, dashes, and horizontal whitespace.

    Preserves line breaks so line-start role tags (``SYSTEM:``, ``ASSISTANT:``)
    can be matched reliably while ``\\s+`` tolerates wrapped or extra whitespace.
    """
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = _ZERO_WIDTH_RE.sub("", cleaned)
    cleaned = _DASH_RE.sub("-", cleaned)
    cleaned = cleaned.lower().translate(_UMLAUT_TABLE)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = (_HORIZ_WS_RE.sub(" ", line).strip() for line in cleaned.split("\n"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1. Instruction override (EN / DE)
# ---------------------------------------------------------------------------
_EN_OVERRIDE_RE = re.compile(
    r"\b(?:ignore|disregard|forget(?:\s+about)?|override|overwrite)\s+"
    r"(?:(?:all|any|every)(?:\s+of)?\s+)?"
    r"(?:(?:the|your|these|those)\s+)?"
    r"(?:"
    r"(?:previous|prior|above|earlier|preceding|original|initial|internal|developer|hidden|existing)\s+"
    r"(?:(?:system|safety|previous|prior|above|earlier|original|initial)\s*-?\s*)?"
    r"(?:instructions?|prompts?|rules?|guidelines?|directives?|polic(?:y|ies))"
    r"|(?:system|safety)\s*-?\s*"
    r"(?:instructions?|prompts?|rules?|guidelines?|directives?|polic(?:y|ies))"
    r")\b"
)

_DE_OVERRIDE_MOD = (
    r"(?:vorherig|bisherig|obig|frueher|urspruenglich|vorangehend|vorangegangen|intern|geheim|bestehend)"
    r"(?:e[nrs]?)?"
)
_DE_OVERRIDE_COMP = r"(?:system|sicherheits)"
_DE_OVERRIDE_NOUN = r"(?:anweisung(?:en)?|instruktion(?:en)?|regel(?:n)?|richtlinie(?:n)?|vorgabe(?:n)?|prompts?)"

_DE_OVERRIDE_RE = re.compile(
    r"\b(?:ignoriere|ignorieren\s+sie|ignoriert"
    r"|vergiss|vergessen\s+sie|vergesst"
    r"|missachte|missachten\s+sie|missachtet"
    r"|umgehe|umgehen\s+sie|umgeht)\s+"
    r"(?:(?:bitte|einfach|jetzt|nun|sofort|ab\s+sofort)\s+){0,2}"
    r"(?:(?:alle[nr]?|saemtliche[nr]?|jede[nrs]?)\s+)?"
    r"(?:(?:die|den|das|deine[nr]?|ihre[nr]?)\s+)?"
    rf"(?:{_DE_OVERRIDE_MOD}(?:\s+|-\s*)(?:{_DE_OVERRIDE_COMP}\s*-?\s*)?{_DE_OVERRIDE_NOUN}"
    rf"|{_DE_OVERRIDE_COMP}\s*-?\s*{_DE_OVERRIDE_NOUN})\b"
)

_DE_OVERRIDE_SOV_RE = re.compile(
    r"\b(?:(?:alle[nr]?|saemtliche[nr]?|die|den|das|deine[nr]?|ihre[nr]?)\s+){1,2}"
    rf"(?:{_DE_OVERRIDE_MOD}(?:\s+|-\s*)(?:{_DE_OVERRIDE_COMP}\s*-?\s*)?{_DE_OVERRIDE_NOUN}"
    rf"|{_DE_OVERRIDE_COMP}\s*-?\s*{_DE_OVERRIDE_NOUN})\s+"
    r"(?:(?:bitte|einfach|jetzt|sofort|komplett|vollstaendig)\s+){0,2}"
    r"(?:ignorieren|vergessen|missachten|umgehen)\b"
)

# ---------------------------------------------------------------------------
# 2. Role / persona hijacking & jailbreak (EN / DE)
# ---------------------------------------------------------------------------
_EN_JAILBREAK_ADJ = r"(?:unrestricted|unfiltered|uncensored|jailbroken|rogue|unbounded|ruleless|dan)"
_EN_ROLE_NOUN = r"(?:assistant|ai|bot|model|agent|chatbot|system)"
_EN_NO_RULES = (
    r"(?:without|with\s+no)\s+(?:any\s+)?"
    r"(?:rules|restrictions|limits|guardrails|filters|safety(?:\s+(?:rules|filters|limits|constraints))?)"
)

_EN_ROLE_HIJACK_RE = re.compile(
    rf"\b(?:"
    rf"you(?:'re|\s+are)\s+(?:(?:from\s+now\s+on|now)\s+)?"
    rf"(?:(?:an?\s+)?{_EN_JAILBREAK_ADJ}(?:\s+{_EN_ROLE_NOUN})?"
    rf"|an?\s+{_EN_ROLE_NOUN}\s+{_EN_NO_RULES}|{_EN_NO_RULES})"
    rf"|(?:act|behave|operate|respond)\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?"
    rf"(?:(?:an?\s+)?{_EN_JAILBREAK_ADJ}(?:\s+{_EN_ROLE_NOUN})?"
    rf"|an?\s+{_EN_ROLE_NOUN}\s+{_EN_NO_RULES})"
    rf"|(?:pretend|roleplay)\s+(?:to\s+be|you(?:'re|\s+are))\s+"
    rf"(?:(?:an?\s+)?{_EN_JAILBREAK_ADJ}(?:\s+{_EN_ROLE_NOUN})?"
    rf"|an?\s+{_EN_ROLE_NOUN}\s+{_EN_NO_RULES})"
    rf")\b"
)

_EN_MODE_RE = re.compile(
    r"\b(?:"
    r"enter\s+(?:the\s+)?(?:developer|jailbreak|unrestricted|unfiltered|god|debug|dan)\s+mode"
    r"|(?:activate|enable|switch\s+to|turn\s+on)\s+(?:the\s+)?(?:jailbreak|unrestricted|unfiltered|god|dan)\s+mode"
    r"|you(?:'re|\s+are)\s+(?:now\s+)?in\s+(?:developer|jailbreak|unrestricted|unfiltered|god|debug|dan)\s+mode"
    r"|jailbreak\s+mode"
    r")\b"
)

_EN_BYPASS_RE = re.compile(
    r"\b(?:"
    r"(?:bypass|circumvent)\s+(?:(?:all|any)(?:\s+of)?\s+)?(?:(?:your|the)\s+)?"
    r"(?:(?:safety|security)(?:\s+(?:checks?|rules?|filters?|controls?|guardrails?|restrictions?|gate))?"
    r"|guardrails?|filters?|restrictions?|escalation(?:\s+(?:gate|rules?|checks?))?|gate)"
    r"|(?:disable|deactivate|turn\s+off)\s+(?:(?:all|any)(?:\s+of)?\s+)?(?:(?:your|the)\s+)?"
    r"(?:(?:safety|security)\s+(?:checks?|rules?|filters?|controls?|guardrails?|restrictions?|gate)"
    r"|guardrails?|escalation(?:\s+(?:gate|rules?|checks?))?)"
    r"|(?:disable|deactivate|turn\s+off)\s+(?:(?:all|any)(?:\s+of)?\s+)?your\s+(?:filters?|restrictions?|gate)"
    r")\b"
)

_DE_JAILBREAK_ADJ = r"(?:uneingeschraenkt|ungefiltert|unzensiert|regellos|regelfrei)(?:e[nrs]?)?"
_DE_ROLE_NOUN = r"(?:assistent(?:in)?|ki|bot|modell|agent|system)"
_DE_NO_RULES = r"ohne\s+(?:jede\s+)?(?:regeln|einschraenkungen|filter|guardrails|sicherheitsregeln|grenzen)"

_DE_ROLE_HIJACK_RE = re.compile(
    rf"\b(?:"
    rf"(?:du\s+bist|sie\s+sind)\s+(?:(?:ab\s+jetzt|ab\s+sofort|jetzt|nun)\s+)?"
    rf"(?:(?:ein(?:e[nrs]?)?\s+)?(?:{_DE_JAILBREAK_ADJ}(?:\s+{_DE_ROLE_NOUN})?|dan\b)"
    rf"|ein(?:e[nrs]?)?\s+{_DE_ROLE_NOUN}\s+{_DE_NO_RULES})"
    rf"|(?:handle|handeln\s+sie|agiere|agieren\s+sie|verhalte\s+dich|verhalten\s+sie\s+sich)\s+"
    rf"(?:(?:ab\s+jetzt|ab\s+sofort|jetzt|nun)\s+)?"
    rf"als\s+(?:(?:ein(?:e[nrs]?)?\s+)?(?:{_DE_JAILBREAK_ADJ}(?:\s+{_DE_ROLE_NOUN})?|dan\b)"
    rf"|ein(?:e[nrs]?)?\s+{_DE_ROLE_NOUN}\s+{_DE_NO_RULES})"
    rf")\b"
)

_DE_MODE_RE = re.compile(
    r"\b(?:"
    r"(?:du\s+bist|sie\s+sind)\s+(?:(?:ab\s+jetzt|ab\s+sofort|jetzt|nun)\s+)?im\s+"
    r"(?:entwickler|developer|jailbreak|uneingeschraenkten|god|debug|dan)\s*-?\s*modus"
    r"|(?:aktiviere|aktivieren\s+sie|wechsle|wechseln\s+sie|starte|starten\s+sie)\s+"
    r"(?:in\s+den\s+|den\s+)?(?:entwickler|developer|jailbreak|uneingeschraenkten|god|dan)\s*-?\s*modus"
    r")\b"
)

_DE_BYPASS_RE = re.compile(
    r"\b(?:umgehe|umgehen\s+sie|deaktiviere|deaktivieren\s+sie|schalte|schalten\s+sie)\s+"
    r"(?:(?:bitte|sofort|jetzt)\s+)?"
    r"(?:(?:alle[nr]?|saemtliche[nr]?)\s+)?"
    r"(?:(?:die|den|das|deine[nr]?|ihre[nr]?)\s+)?"
    r"(?:sicherheits\s*-?\s*(?:regeln?|pruefung(?:en)?|richtlinien?|filter|guardrails?|gate|checks?|sperren?)"
    r"|guardrails?|filter(?:n)?|einschraenkung(?:en)?"
    r"|eskalation(?:s\s*-?\s*(?:gate|regeln?|pruefung(?:en)?))?)\b"
)

# ---------------------------------------------------------------------------
# 3. Policy spoofing (EN / DE)
# ---------------------------------------------------------------------------
_EN_POLICY_SPOOF_RE = re.compile(
    r"\b(?:state|declare|present|treat)\s+"
    r"(?:"
    r"(?:it|this|that|the\s+(?:above|following))\s+(?:(?:as|to\s+be)\s+)?"
    r"|as\s+"
    r"|that\s+(?:it|this|that)\s+is\s+"
    r")"
    r"(?:an?\s+)?(?:(?:official|binding|approved|standard)\s+)?"
    r"(?:company|corporate)\s+polic(?:y|ies)\b"
)

_DE_POLICY_SPOOF_RE = re.compile(
    r"\b(?:stelle|stellen\s+sie|erklaere|erklaeren\s+sie|gib|geben\s+sie"
    r"|behandle|behandeln\s+sie|praesentiere|praesentieren\s+sie)\s+"
    r"(?:bitte\s+)?"
    r"(?:(?:es|dies|das|dieses)\s+)?"
    r"als\s+(?:eine\s+)?(?:(?:offizielle[nr]?|verbindliche[nr]?|gueltige[nr]?)\s+)?"
    r"(?:unternehmens|firmen|konzern|geschaefts)\s*-?\s*(?:richtlinie(?:n)?|politik|policy)\b"
)

# ---------------------------------------------------------------------------
# 4. System prompt extraction (EN / DE)
# ---------------------------------------------------------------------------
_EN_PROMPT_LEAK_RE = re.compile(
    r"(?<!\bnot\s)(?<!n't\s)(?<!\bnever\s)"
    r"\b(?:(?:reveal|show|print(?:\s+out)?|dump(?:\s+out)?|output|repeat|leak|display|disclose|expose)"
    r"(?:\s+(?:me|us))?|(?:tell|give)\s+(?:me|us))\s+"
    r"(?:all\s+(?:of\s+)?)?(?:(?:your|the)\s+)?"
    r"(?:(?:full|entire|exact|complete|verbatim)\s+)?"
    r"(?:system\s*-?\s*(?:prompts?|instructions?)"
    r"|(?:hidden|internal|secret|initial|original|developer)\s+(?:system\s*-?\s*)?(?:prompts?|instructions?))\b"
)

_DE_PROMPT_LEAK_RE = re.compile(
    r"\b(?:zeige?|zeigen\s+sie|gib|geben\s+sie|nenne|nennen\s+sie"
    r"|verrate|verraten\s+sie|offenbare|offenbaren\s+sie|wiederhole|wiederholen\s+sie)\s+"
    r"(?:(?:mir|uns|bitte)\s+){0,2}"
    r"(?:(?:alle[nr]?|saemtliche[nr]?)\s+)?"
    r"(?:(?:dein(?:e[nrm]?)?|ihr(?:e[nrm]?)?|den|die|das)\s+)?"
    r"(?:(?:vollstaendig|komplett|genau)(?:e[nrs]?)?\s+)?"
    r"(?:system\s*-?\s*(?:prompts?|anweisung(?:en)?|instruktion(?:en)?)"
    r"|(?:geheim|intern|urspruenglich|versteckt)(?:e[nrs]?)?\s+(?:system\s*-?\s*)?"
    r"(?:anweisung(?:en)?|instruktion(?:en)?|prompts?))\b"
)

# ---------------------------------------------------------------------------
# 5. Delimiter / role-tag / JSON-output tampering
# ---------------------------------------------------------------------------
_FAKE_DELIMITER_RE = re.compile(
    r"<<\s*/?\s*sys\s*>>"
    r"|\[\s*/?\s*inst\s*\]"
    r"|<\|(?:im_start|im_end|system|assistant|user|endoftext)\|>"
    r"|</?\s*(?:system|system_prompt)\s*>"
)

_ROLE_TAG_DIRECTIVE_RE = re.compile(
    r"^(?:system|assistant)[ \t]*:[ \t]*"
    r"(?:(?:please|now|important|note|attention|update|bitte|achtung|hinweis|ab\s+sofort)\b[ \t,:!-]*){0,2}"
    r"(?:you(?:'re|\s+are)|ignore|disregard|forget|override|new\s+instructions?|always|never"
    r"|respond|reply|output|set\b|do\s+not|don't"
    r"|du\s+bist|sie\s+sind|ignoriere|ignorieren|vergiss|vergessen|neue\s+anweisungen?"
    r"|immer|niemals|antworte|antworten|setze\b)",
    re.MULTILINE,
)

_OUTPUT_TAMPER_RE = re.compile(
    r"\b(?:set|setze|setzen\s+sie|force|override|output|return)\s+"
    r'["\']?(?:refused|escalation|tier|grounded|injection_flags|guard_findings|escalation_reasons)["\']?'
    r"\s*(?:==?|:|\bto\b|\bauf\b|\bas\b)\s*"
    r'["\']?(?:false|true|auto[_ -]?draft|none|empty|\[\])(?![a-z0-9_])["\']?'
    r'|"(?:escalation|tier)"\s*:\s*"auto[_ -]?draft"'
    r'|"(?:injection_flags|guard_findings|escalation_reasons)"\s*:\s*\[\]'
)

_RULES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (LABEL_OVERRIDE, (_EN_OVERRIDE_RE, _DE_OVERRIDE_RE, _DE_OVERRIDE_SOV_RE)),
    (
        LABEL_JAILBREAK,
        (
            _EN_ROLE_HIJACK_RE,
            _EN_MODE_RE,
            _EN_BYPASS_RE,
            _DE_ROLE_HIJACK_RE,
            _DE_MODE_RE,
            _DE_BYPASS_RE,
        ),
    ),
    (LABEL_POLICY_SPOOF, (_EN_POLICY_SPOOF_RE, _DE_POLICY_SPOOF_RE)),
    (LABEL_PROMPT_LEAK, (_EN_PROMPT_LEAK_RE, _DE_PROMPT_LEAK_RE)),
    (LABEL_DELIMITER, (_FAKE_DELIMITER_RE, _ROLE_TAG_DIRECTIVE_RE, _OUTPUT_TAMPER_RE)),
)


def _matches_any(normalized: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(normalized) is not None for pattern in patterns)


def detect_injection(text: str) -> list[str]:
    """Return deduplicated human-readable labels for each prompt-injection pattern matched."""
    if not text or not text.strip():
        return []
    normalized = _normalize(text)
    return [label for label, patterns in _RULES if _matches_any(normalized, patterns)]
