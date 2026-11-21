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
