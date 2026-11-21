"""Team contract tests: the interfaces everyone codes against. Offline, no dataset, ~1 s.

Owner: A (Je). Every teammate runs `make team-test` before pushing. If you need to change one of
these contracts, ask the owner of the function and A first (docs/team/README.md, "Changing a contract").
"""

from __future__ import annotations

import inspect

import pandas as pd

from agent.llm_router import LLMRouter
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from sentinel import claims, dataset, escalation, explain, feedback, injection, smart_queue, thresholds, ticket_store
from sentinel.ingest_tickets import ticket_chunk
from sentinel.pipeline import SentinelAgent
from sentinel.triage import HeadPrediction, TriagePrediction
from sentinel.writer import build_user_prompt, extractive_draft, verify_citations
from shared.contracts import GuardFinding, LabelCorrection, SentinelResult
from shared.settings import Settings


def _params(fn) -> list[str]:
    return list(inspect.signature(fn).parameters)


def test_function_signatures_are_stable():
    assert _params(explain.explain) == ["model", "text", "top_n"]
    assert _params(injection.detect_injection) == ["text"]
    assert _params(claims.check_claims) == ["reply", "verified"]
    assert _params(escalation.decide_tier) == ["decision", "reasons"]
    assert _params(thresholds.load) == ["settings"]
    assert _params(feedback.record_correction) == ["c"]
    assert _params(feedback.retrain_challenger) == []
    assert _params(ticket_store.add_ticket) == ["subject", "body", "source"]
    assert _params(build_user_prompt) == ["subject", "body", "language", "precedents"]
    assert _params(extractive_draft) == ["language", "precedents"]
    assert _params(verify_citations) == ["draft", "precedents"]
    for name in ("submit", "stats", "snapshot", "set_concurrency", "shutdown"):
        assert hasattr(smart_queue.SmartQueue, name)


def test_return_types():
    assert isinstance(explain.explain(None, "VPN down"), dict)
    assert isinstance(injection.detect_injection("hello"), list)
    found = claims.check_claims("We will refund you within 48 hours.", [])
    assert isinstance(found, list) and all(isinstance(g, GuardFinding) for g in found)
    assert escalation.decide_tier("AUTO_DRAFT", []) in ("AUTO_DRAFT", "AGENT_REVIEW", "PAGE_ONCALL")
    assert set(thresholds.load(Settings())) == set(thresholds.KEYS)
    assert isinstance(feedback.retrain_challenger(), dict)
    assert "status" in feedback.retrain_challenger()


def test_validation_slice_is_the_tail_of_kb():
    kb = pd.DataFrame({"ticket_id": [f"TKT-{i:05d}" for i in range(100)]})
    train, val = dataset.split_train_val(kb, 0.1)
    assert len(train) == 90 and len(val) == 10
    assert val["ticket_id"].iloc[0] == "TKT-00090"
    assert set(train["ticket_id"]).isdisjoint(val["ticket_id"])


def test_ticket_store_flow():
    ticket_store.reset()
    tid = ticket_store.add_ticket(None, "VPN is down", source="preset")
    assert ticket_store.get_ticket(tid).status == "new"
    ticket_store.set_status(tid, "queued")
    assert [r.ticket_id for r in ticket_store.list_tickets("queued")] == [tid]
    ticket_store.reset()


def test_label_correction_roundtrip(tmp_path, monkeypatch):
    s = Settings(corrections_path=tmp_path / "c.jsonl")
    monkeypatch.setattr(feedback, "get_settings", lambda: s)
    feedback.record_correction(LabelCorrection(ticket_id="SD-1", text="x", head="priority",
                                               predicted="low", corrected="high"))
    assert feedback.list_corrections()[0].corrected == "high"


class _FakeTriage:
    """Stands in for the trained model so the pipeline runs without the dataset."""

    def predict(self, subject, body):
        def head(label, conf):
            return HeadPrediction(label=label, confidence=conf, probabilities={label: conf})
        return TriagePrediction(type=head("Incident", 0.9), queue=head("Technical Support", 0.8),
                                priority=head("high", 0.85), language="en", language_confidence=0.99)


def test_pipeline_end_to_end_with_stubs():
    settings = Settings(llm_provider="extractive", llm_fallback="", warm_up=False)
    store = VectorStore(":memory:", HashEmbedder())
    row = pd.Series({"ticket_id": "TKT-00001", "subject": "VPN down", "body": "VPN gateway refuses connections",
                     "answer": "Restarted the VPN gateway and cleared stale sessions; connections stable since.",
                     "type": "Incident", "queue": "Technical Support", "priority": "high", "language": "en"})
    store.add([ticket_chunk(row)], embed_texts=["VPN down\nVPN gateway refuses connections"])
    agent = SentinelAgent(settings=settings, store=store, router=LLMRouter(settings), triage_model=_FakeTriage())

    result = agent.triage("VPN down", "Our VPN gateway refuses connections. Mail me at a@b.de")

    assert isinstance(result, SentinelResult)
    assert result.precedents and result.precedents[0].ticket_id == "TKT-00001"
    assert result.tier in ("AUTO_DRAFT", "AGENT_REVIEW", "PAGE_ONCALL")
    assert result.escalation == "ESCALATE"  # high-priority Incident -> R1
    assert any(r.startswith("R1") for r in result.escalation_reasons)
    assert "<EMAIL>" in result.pii_masked_body
    assert result.grounded and result.cited_ticket_ids == ["TKT-00001"]
    assert isinstance(result.explanations, dict) and isinstance(result.guard_findings, list)
