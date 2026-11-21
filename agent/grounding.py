"""Reject anything the model says that the retrieved context does not literally support.

A DraftFinding becomes a Finding only if:
  1. its chunk_id is one of the chunks actually given to the model,
  2. its evidence_quote appears verbatim (whitespace/case/curly-quote-insensitive) in that chunk,
  3. its claim is consistent with that quote (check_claim: shared wording, same numbers, same polarity),
  4. its confidence is in [0, 1] and >= the configured threshold.

Source and line/timestamp are taken from the stored chunk, never from the model.

check_claim is a cheap, deterministic guard, not entailment: it catches the common ways a real quote
gets attached to a wrong claim (different number, flipped negation, unrelated text). The UI therefore
shows the verified quote as the answer and the claim only as a labelled summary of it.
"""

import re

from shared.contracts import Chunk, DraftAnswer, Finding, Rejection, RejectionKind, RetrievedChunk

MIN_QUOTE_CHARS = 8

_NEGATIONS = {
    "not", "no", "never", "none", "nobody", "nothing", "neither", "nor", "cannot", "without",
    "prohibited", "forbidden", "banned", "illegal",
}
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20",
    "thirty": "30", "forty": "40", "forty-five": "45", "fifty": "50", "sixty": "60", "ninety": "90",
    "hundred": "100", "first": "1", "second": "2", "third": "3", "half": "0.5", "once": "1", "twice": "2",
}
_STOPWORDS = set(
    "a an the is are was were be been being of to in on for and or but with by at from as it its this that "
    "these those what which who whom how why when where do does did can could should would will may might "
    "must shall i you we they he she my your our their me us them there here about into than then so if "
    "yes also any all each per via".split()
)


def normalize(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().strip("\"'").lower()


def _tokens(text: str) -> list[str]:
    text = normalize(text).replace("n't", " not")
    return re.findall(r"\d+(?:[.,]\d+)*|[a-z]+(?:-[a-z]+)?", text)


def _numbers(tokens: list[str]) -> set[str]:
    out = set()
    for t in tokens:
        if t[0].isdigit():
            out.add(t.replace(",", "").rstrip("."))
        elif t in _NUMBER_WORDS:
            out.add(_NUMBER_WORDS[t])
    return out


def check_claim(claim: str, quote: str) -> str | None:
    """Return why `claim` is not supported by `quote`, or None if it is consistent with it."""
    c, q = _tokens(claim), _tokens(quote)
    if not c:
        return "claim is empty"
    if c[0] in {"yes", "no"}:  # "No, permits last at most 30 days" answers the question; not a negation
        c = c[1:]
    missing = _numbers(c) - _numbers(q)
    if missing:
        return f"claim states {', '.join(sorted(missing))}, which the quote does not"
    if bool(_NEGATIONS & set(c)) != bool(_NEGATIONS & set(q)):
        return "claim and quote have opposite polarity (one is negated)"
    content = {t for t in c if t not in _STOPWORDS and t not in _NEGATIONS and len(t) > 2}
    q_set = set(q)
    # Light stemming so "repaired"/"repairs"/"repair" match.
    stem = lambda t: re.sub(r"(ing|ed|es|s)$", "", t)  # noqa: E731
    if content and not ({stem(t) for t in content} & {stem(t) for t in q_set}):
        return "claim shares no wording with the quote"
    return None


def refine_locator(chunk: Chunk, quote: str) -> str:
    """Narrow a line-range chunk locator to the lines the quote actually spans.

    Matches the way grounding does (case-, whitespace- and curly-quote-insensitive), so a quote that
    passed verification also gets a precise line range, not just the whole chunk's.
    """
    start = chunk.metadata.get("start_line")
    if start is None:
        return chunk.locator
    words = normalize(quote).split()
    if not words:
        return chunk.locator
    text = chunk.text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    m = re.search(r"\s+".join(re.escape(w) for w in words), text, re.IGNORECASE)
    if not m:
        return chunk.locator
    first = int(start) + text.count("\n", 0, m.start())
    last = first + text.count("\n", m.start(), m.end())
    return f"L{first}" if first == last else f"L{first}-L{last}"


def ground(
    draft: DraftAnswer, retrieved: list[RetrievedChunk], min_confidence: float
) -> tuple[list[Finding], list[Rejection]]:
    by_id = {r.chunk.id: r.chunk for r in retrieved}
    findings: list[Finding] = []
    rejected: list[Rejection] = []

    for f in draft.findings:
        chunk = by_id.get(f.chunk_id)
        quote = normalize(f.evidence_quote)
        reason: str | None = None
        kind: RejectionKind | None = None
        if chunk is None:
            reason, kind = "cites a chunk that was not in the context", "unknown_chunk"
        elif len(quote) < MIN_QUOTE_CHARS:
            reason, kind = "evidence quote missing or too short", "quote_too_short"
        elif quote not in normalize(chunk.text):
            reason, kind = "evidence quote not found verbatim in the cited chunk", "quote_not_found"
        elif mismatch := check_claim(f.claim, f.evidence_quote):
            reason, kind = mismatch, "claim_mismatch"
        elif not 0.0 <= f.confidence_score <= 1.0:
            reason, kind = "confidence score outside [0, 1]", "bad_confidence"
        elif f.confidence_score < min_confidence:
            reason = f"confidence {f.confidence_score:.2f} below threshold {min_confidence:.2f}"
            kind = "low_confidence"

        if reason:
            rejected.append(Rejection(finding=f, reason=reason, kind=kind))
            continue

        findings.append(
            Finding(
                claim=f.claim,
                evidence_source=chunk.source,
                line_or_timestamp=refine_locator(chunk, f.evidence_quote),
                evidence_quote=f.evidence_quote,
                confidence_score=f.confidence_score,
                chunk_id=chunk.id,
            )
        )
    return findings, rejected
