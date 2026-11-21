"""SentinelDesk end to end: triage -> retrieve -> gate -> grounded draft -> verify.

    from sentinel.pipeline import SentinelAgent
    result = SentinelAgent().triage("VPN down for all remote staff", "Nobody can reach the EMR...")

Order matters. The classifier and the gate run *before* the LLM, so a high-priority incident is
on an engineer's screen in ~1 s whatever the model is doing, and a ticket with no precedent never
reaches a generator that would happily invent one.

    python -m sentinel.pipeline "my VPN is down since the firewall update"
"""

from __future__ import annotations

import logging
import time

from pydantic import ValidationError

from agent.llm_router import LLMError, LLMRouter
from memory.embedder import get_embedder
from memory.store import VectorStore
from sentinel import claims, escalation, explain, injection, pii, thresholds
from sentinel.dataset import ticket_text
from sentinel.triage import TriageModel, get_model

# The writer (prompt, fallback draft, citation checks) lives in sentinel/writer.py (owner D).
# Re-exported here so older imports such as `from sentinel.pipeline import SYSTEM_PROMPT` still work.
from sentinel.writer import (  # noqa: F401
    MIN_QUOTE_CHARS,
    PROMPT_ANSWER_CHARS,
    PROMPT_BODY_CHARS,
    PROMPT_PRECEDENTS,
    SYSTEM_PROMPT,
    build_user_prompt,
    extractive_draft,
    verify_citations,
)
from shared.contracts import (
    Precedent,
    ProviderAttempt,
    SentinelDraft,
    SentinelResult,
    TriageLabels,
)
from shared.settings import Settings, get_settings

log = logging.getLogger(__name__)


def _safe(fn, default, *args, **kwargs):
    """Call a teammate's module without letting a half-built feature crash triage."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - one broken add-on must never take the pipeline down
        log.warning("%s failed: %s", getattr(fn, "__name__", fn), e)
        return default


def _precedent_from_chunk(chunk, score: float) -> Precedent:
    m = chunk.metadata
    body = chunk.text.split("Body:", 1)[-1].split("Resolution:", 1)[0].strip()
    return Precedent(
        ticket_id=m.get("ticket_id", chunk.id),
        similarity=round(float(score), 4),
        subject=m.get("subject", ""),
        body_snippet=body[:400],
        answer=m.get("answer", ""),
        type=m.get("type", ""),
        queue=m.get("queue", ""),
        priority=m.get("priority", ""),
        language=m.get("language", ""),
    )


class SentinelAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        store: VectorStore | None = None,
        router: LLMRouter | None = None,
        triage_model: TriageModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or VectorStore(self.settings.sentinel_memory_path, get_embedder(self.settings))
        self.router = router or LLMRouter(self.settings)
        self.triage_model = triage_model or get_model()
        self._down_until: dict[str, float] = {}

    # -- plumbing ----------------------------------------------------------

    def provider_chain(self, provider: str | None = None, fallback: bool = True) -> list[str]:
        chain = [provider or self.settings.llm_provider]
        if fallback:
            chain += [p.strip() for p in self.settings.llm_fallback.split(",") if p.strip()]
        return list(dict.fromkeys(chain))

    def warm_up(self) -> dict[str, str]:
        status: dict[str, str] = {}
        if hasattr(self.store.embedder, "warm_up"):
            try:
                self.store.embedder.warm_up()
                status["embedder"] = "ok"
            except Exception as e:
                status["embedder"] = str(e)[:200]
        for p in self.provider_chain():
            if p == "ollama":
                try:
                    self.router.warm_up(p)
                    status[p] = "ok"
                except LLMError as e:
                    status[p] = str(e)[:200]
        try:
            self.store.search("warm up", k=1)  # builds the vector matrix cache (~70 MB read)
            status["index"] = f"{self.store.count():,} tickets"
        except Exception as e:  # never let a cold embedder stop the console from opening
            status["index"] = str(e)[:200]
        return status

    def _generate(self, provider: str, subject: str, body: str, language: str,
                  precedents: list[Precedent]) -> SentinelDraft:
        if provider == "extractive":
            return extractive_draft(language, precedents)
        return self.router.complete(
            SYSTEM_PROMPT, build_user_prompt(subject, body, language, precedents),
            SentinelDraft, provider=provider,
        )

    # -- main entry point ---------------------------------------------------

    def triage(
        self,
        subject: str | None,
        body: str,
        k: int | None = None,
        provider: str | None = None,
        fallback: bool = True,
        draft: bool = True,
    ) -> SentinelResult:
        """Triage one ticket. Never raises: a failure becomes an escalation with a reason."""
        t_all = time.perf_counter()
        stages: dict[str, float] = {}
        text = ticket_text({"subject": subject or "", "body": body or ""})

        # 1. classify (always, ~1 ms) -------------------------------------
        t = time.perf_counter()
        pred = self.triage_model.predict(subject, body)
        stages["triage_ms"] = _ms(t)
        triage = TriageLabels(
            type=pred.type.label, queue=pred.queue.label, priority=pred.priority.label,
            type_confidence=round(pred.type.confidence, 4),
            queue_confidence=round(pred.queue.confidence, 4),
            priority_confidence=round(pred.priority.confidence, 4),
            triage_confidence=round(pred.confidence, 4),
            type_probabilities=pred.type.probabilities,
            queue_probabilities=pred.queue.probabilities,
            priority_probabilities=pred.priority.probabilities,
        )
        # Why-this-label words (owner B). Returns {} until sentinel/explain.py is implemented.
        explanations = _safe(explain.explain, {}, self.triage_model, text)

        # 2. retrieve precedents -------------------------------------------
        t = time.perf_counter()
        retrieval_error: str | None = None
        precedents: list[Precedent] = []
        try:
            hits = self.store.search(text, k or self.settings.sentinel_top_k)
            precedents = [_precedent_from_chunk(h.chunk, h.score) for h in hits]
        except Exception as e:  # embedder down: escalate rather than guess
            retrieval_error = f"retrieval failed: {str(e)[:200]}"
        stages["retrieval_ms"] = _ms(t)
        top_similarity = precedents[0].similarity if precedents else 0.0

        # 3. pre-draft gate -------------------------------------------------
        # Thresholds come from data/sentinel/thresholds.json when owner A has tuned them on the
        # validation slice, otherwise from Settings.
        th = _safe(thresholds.load, {
            "triage_confidence_min": self.settings.triage_confidence_min,
            "retrieval_similarity_min": self.settings.retrieval_similarity_min,
            "high_priority_alert_probability": self.settings.high_priority_alert_probability,
        }, self.settings)
        gate = escalation.pre_draft_gate(
            predicted_type=triage.type,
            predicted_priority=triage.priority,
            triage_confidence=triage.triage_confidence,
            high_priority_probability=triage.priority_probabilities.get("high", 0.0),
            top_similarity=top_similarity,
            ticket_text=text,
            triage_confidence_min=th["triage_confidence_min"],
            retrieval_similarity_min=th["retrieval_similarity_min"],
            high_priority_alert_probability=th["high_priority_alert_probability"],
        )
        if retrieval_error:
            gate = escalation.GateOutcome("ESCALATE", [*gate.reasons, f"R4 {retrieval_error}"])
        # R7 prompt injection (owner D). Returns [] until sentinel/injection.py is implemented.
        injection_flags = _safe(injection.detect_injection, [], text)
        if injection_flags:
            gate = escalation.GateOutcome(
                "ESCALATE", [*gate.reasons, *(f"R7 prompt injection: {f}" for f in injection_flags)]
            )

        if self.settings.mask_pii_in_prompts:
            masked_body, found = pii.mask_pii(body or "")
            masked_subject, found_subject = pii.mask_pii(subject or "")
            for key, n in found_subject.items():
                found[key] = found.get(key, 0) + n
        else:
            masked_subject, masked_body, found = subject or "", body or "", {}

        result = SentinelResult(
            subject=subject, body=body,
            detected_language=pred.language if pred.language in ("en", "de") else "en",
            language_confidence=round(pred.language_confidence, 4),
            triage=triage, escalation=gate.decision, escalation_reasons=gate.reasons,
            precedents=precedents, top_similarity=top_similarity,
            pii_masked=bool(found), pii_found=found,
            error=retrieval_error,
            explanations=explanations,
            injection_flags=injection_flags,
            pii_masked_body=ticket_text({"subject": masked_subject, "body": masked_body}),
        )
        result.tier = _safe(escalation.decide_tier, None, result.escalation, result.escalation_reasons)

        # 4. draft (still drafted when escalating, as suggested notes for the human) ----
        if not draft or not precedents:
            result.stage_latency_ms = stages
            result.latency_ms = _ms(t_all)
            return result

        t = time.perf_counter()
        chain = self.provider_chain(provider, fallback)
        attempts: list[ProviderAttempt] = []
        drafted: SentinelDraft | None = None
        used = chain[0]
        for i, p in enumerate(chain):
            is_last = i == len(chain) - 1
            if not is_last and time.monotonic() < self._down_until.get(p, 0.0):
                attempts.append(ProviderAttempt(provider=p, model=self.router.model_name(p), ok=False,
                                                skipped=True, error="cooling down after a recent failure"))
                continue
            t_p = time.perf_counter()
            try:
                drafted = self._generate(p, masked_subject, masked_body, result.detected_language, precedents)
            except (LLMError, ValidationError) as e:
                if self.settings.llm_cooldown_s > 0:
                    self._down_until[p] = time.monotonic() + self.settings.llm_cooldown_s
                attempts.append(ProviderAttempt(provider=p, model=self.router.model_name(p), ok=False,
                                                error=str(e)[:300], latency_ms=_ms(t_p)))
                continue
            self._down_until.pop(p, None)
            attempts.append(ProviderAttempt(provider=p, model=self.router.model_name(p), ok=True,
                                            latency_ms=_ms(t_p)))
            used = p
            break
        stages["generation_ms"] = _ms(t)

        if drafted is None:
            result.attempts = attempts
            result.provider, result.model = used, self.router.model_name(used)
            result.error = " | ".join(f"{a.provider}: {a.error}" for a in attempts if not a.ok)
            result.escalation_reasons = [*gate.reasons, "R6 no model produced a draft"]
            result.escalation = "ESCALATE"
            result.tier = _safe(escalation.decide_tier, None, result.escalation, result.escalation_reasons)
            result.stage_latency_ms = stages
            result.latency_ms = _ms(t_all)
            return result

        # 5. verify every citation, then the post-draft gate ----------------
        t = time.perf_counter()
        verified, rejected = verify_citations(drafted, precedents)
        stages["grounding_ms"] = _ms(t)
        grounded = bool(verified)
        final = escalation.post_draft_gate(gate, grounded, drafted.refused, drafted.refusal_reason)
        # Number-and-promise guard (owner D). Returns [] until sentinel/claims.py is implemented.
        guard_findings = _safe(claims.check_claims, [], drafted.draft_reply or "", verified)
        if guard_findings:
            final = escalation.GateOutcome("ESCALATE", [
                *final.reasons,
                *(f"R6 unbacked {g.kind} in draft: '{g.text}'" for g in guard_findings),
            ])
        stages["grounding_ms"] = _ms(t)

        result.guard_findings = guard_findings
        result.briefing = (drafted.briefing or "").strip()
        result.draft_reply = drafted.draft_reply.strip() or None
        result.cited_ticket_ids = [v.ticket_id for v in verified]
        result.verified_citations = verified
        result.rejected_citations = rejected
        result.grounded = grounded
        result.refused = drafted.refused
        result.refusal_reason = drafted.refusal_reason
        result.escalation = final.decision
        result.escalation_reasons = final.reasons
        result.tier = _safe(escalation.decide_tier, None, result.escalation, result.escalation_reasons)
        result.provider = used
        result.model = self.router.model_name(used)
        result.fell_back = used != chain[0]
        result.attempts = attempts
        result.stage_latency_ms = stages
        result.latency_ms = _ms(t_all)
        return result


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


if __name__ == "__main__":
    import sys

    body_arg = " ".join(sys.argv[1:]) or "Our VPN has been down since the firewall update this morning."
    out = SentinelAgent().triage(None, body_arg)
    print(out.model_dump_json(indent=2, exclude={"precedents": {"__all__": {"answer", "body_snippet"}}}))
