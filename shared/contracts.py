"""The JSON contract between ingestion, agent, eval, API and UI.

Flow:
    ingest_*  ->  Chunk                      (stored in memory.store)
    retrieve  ->  RetrievedChunk
    LLM       ->  DraftAnswer[DraftFinding]  (untrusted model output)
    grounding ->  Finding | Rejection        (only verified claims survive)
    agent     ->  AgentAnswer                (what the API returns and the UI renders)

Change these models in one place; run `make schema` to regenerate shared/schema/*.json.
"""

from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["code", "doc", "media", "ticket"]


class Chunk(BaseModel):
    id: str = Field(description="Stable id: hash of source + locator.")
    source: str = Field(description="File path (posix, relative to ingest root) or URL.")
    kind: SourceKind
    text: str
    locator: str = Field(description='Where in the source: "L10-L42", "p3", or "00:01:05-00:01:35".')
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float


class DraftFinding(BaseModel):
    """What the model is asked to produce. Never shown to users without grounding."""

    claim: str
    chunk_id: str = Field(description="id of the context chunk that supports the claim.")
    evidence_quote: str = Field(description="A verbatim, contiguous span copied from that chunk.")
    confidence_score: float = Field(description="0.0-1.0: how directly the quote supports the claim.")


class DraftAnswer(BaseModel):
    findings: list[DraftFinding] = Field(default_factory=list)
    abstain: bool = Field(default=False, description="True when the context does not answer the question.")


class Finding(BaseModel):
    """A claim that passed grounding. This is the user-facing unit."""

    claim: str
    evidence_source: str
    line_or_timestamp: str
    evidence_quote: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    chunk_id: str


RejectionKind = Literal[
    "unknown_chunk",     # cites a chunk that was not in the context
    "quote_too_short",   # evidence quote missing or too short to verify
    "quote_not_found",   # quote is not verbatim in the cited chunk (fabricated citation)
    "claim_mismatch",    # quote is real, but the claim says something the quote does not
    "bad_confidence",    # confidence outside [0, 1]
    "low_confidence",    # below MIN_CONFIDENCE (the model itself was unsure)
]


class Rejection(BaseModel):
    finding: DraftFinding
    reason: str
    kind: RejectionKind = "quote_not_found"


class ProviderAttempt(BaseModel):
    """One step of the fallback chain."""

    provider: str
    model: str
    ok: bool
    skipped: bool = Field(default=False, description="Not called: provider is cooling down after a recent failure.")
    error: str | None = None
    latency_ms: float = 0.0


class AgentAnswer(BaseModel):
    question: str
    findings: list[Finding]
    rejected: list[Rejection] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    abstained: bool
    provider: str = Field(description="The provider that produced this answer (after any fallback).")
    model: str
    latency_ms: float
    fell_back: bool = Field(default=False, description="True if the requested provider failed and another answered.")
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    error: str | None = Field(default=None, description="Set only when every provider in the chain failed.")


class AskRequest(BaseModel):
    question: str
    k: int | None = None
    provider: str | None = None
    fallback: bool = True


# --------------------------------------------------------------------------
# SentinelDesk: incident triage, escalation and precedent-grounded resolution.
#
#   TicketInput -> triage (classifier) -> retrieve precedents -> SentinelDraft (LLM, untrusted)
#               -> citation grounding + escalation gate -> SentinelResult (what the UI renders)
# --------------------------------------------------------------------------

Language = Literal["en", "de"]
EscalationDecision = Literal["AUTO_DRAFT", "ESCALATE"]


class TicketInput(BaseModel):
    subject: str | None = Field(default=None, description="May be null/empty: 13% of the dataset has no subject.")
    body: str
    k: int | None = Field(default=None, description="How many precedents to retrieve.")
    provider: str | None = None
    fallback: bool = True


class Precedent(BaseModel):
    """A past resolved ticket offered as evidence. Everything here comes from the index."""

    ticket_id: str
    similarity: float
    subject: str
    body_snippet: str
    answer: str
    type: str
    queue: str
    priority: str
    language: str


class DraftCitation(BaseModel):
    """Model output: which past ticket backs a sentence, and the span it was taken from."""

    ticket_id: str = Field(description="A TKT-xxxxx id from the retrieved precedents.")
    evidence_quote: str = Field(description="A verbatim, contiguous span copied from that ticket's resolution.")


class SentinelDraft(BaseModel):
    """Raw LLM output. Nothing here reaches an operator before citation grounding.

    Field order is deliberate: a model fills a JSON schema top to bottom, so it must copy its
    evidence *before* it writes the reply. Asked the other way round it writes fluent prose first
    and then looks for quotes to justify it, which is exactly the failure mode being prevented.
    """

    reply_language: Language = Field(description="The requester's language, detected from their text.")
    refused: bool = Field(description="True when the precedents do not support a safe answer.")
    refusal_reason: str = Field(default="", description="One short sentence; empty unless refused.")
    citations: list[DraftCitation] = Field(
        description="Required unless refused: the quotes the reply is built from. [] only when refused."
    )
    draft_reply: str = Field(default="", description="The reply, written in reply_language. Empty when refused.")


class VerifiedCitation(BaseModel):
    """A citation whose quote was found verbatim in the cited ticket's historical resolution."""

    ticket_id: str
    evidence_quote: str
    similarity: float


CitationRejectionKind = Literal[
    "unknown_ticket",    # cites a ticket that was not retrieved (invented precedent)
    "quote_too_short",   # quote missing or too short to verify
    "quote_not_found",   # quote is not verbatim in that ticket's resolution
]


class CitationRejection(BaseModel):
    citation: DraftCitation
    reason: str
    kind: CitationRejectionKind


class TriageLabels(BaseModel):
    type: str
    queue: str
    priority: str
    type_confidence: float
    queue_confidence: float
    priority_confidence: float
    triage_confidence: float = Field(description="The weakest head; what the escalation gate thresholds on.")
    type_probabilities: dict[str, float] = Field(default_factory=dict)
    queue_probabilities: dict[str, float] = Field(default_factory=dict)
    priority_probabilities: dict[str, float] = Field(default_factory=dict)


class SentinelResult(BaseModel):
    """One triaged ticket, end to end. This is what the console and the API return."""

    subject: str | None
    body: str
    detected_language: Language
    language_confidence: float

    triage: TriageLabels
    escalation: EscalationDecision
    escalation_reasons: list[str] = Field(default_factory=list)

    precedents: list[Precedent] = Field(default_factory=list)
    top_similarity: float = 0.0

    draft_reply: str | None = None
    cited_ticket_ids: list[str] = Field(default_factory=list)
    verified_citations: list[VerifiedCitation] = Field(default_factory=list)
    rejected_citations: list[CitationRejection] = Field(default_factory=list)
    grounded: bool = Field(default=False, description="At least one citation survived verification.")
    refused: bool = False
    refusal_reason: str = ""

    pii_masked: bool = False
    pii_found: dict[str, int] = Field(default_factory=dict)

    provider: str = ""
    model: str = ""
    fell_back: bool = False
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    error: str | None = None

    latency_ms: float = 0.0
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)


class EvalCase(BaseModel):
    id: str
    question: str
    expected_sources: list[str] = Field(
        default_factory=list, description="Substrings; a finding counts as correct if its source contains one."
    )
    expected_quote_contains: list[str] = Field(
        default_factory=list,
        description="Case-insensitive substrings; the answer is correct only if a verified quote contains one.",
    )
    should_abstain: bool = False
    tags: list[str] = Field(default_factory=list)


class EvalRecord(BaseModel):
    case: EvalCase
    answer: AgentAnswer
    abstain_correct: bool
    retrieval_hit: bool | None = Field(description="An expected source was among the retrieved chunks (recall@k).")
    source_hit: bool
    content_hit: bool | None = Field(description="A verified quote contains an expected substring.")
    source_precision: float | None
    passed: bool
