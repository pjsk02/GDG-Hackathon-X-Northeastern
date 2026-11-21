"""Tests for Step 2: UI shell, agent board grouping, and side panel rendering."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from agent.llm_router import LLMRouter
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from sentinel import ticket_store
from sentinel.ingest_tickets import ticket_chunk
from sentinel.pipeline import SentinelAgent
from sentinel.triage import HeadPrediction, TriagePrediction
from shared.contracts import SentinelResult, TriageLabels
from shared.settings import Settings
from ui.shared import build_board_dataframe, format_waiting_time, group_tickets_by_tier, triage_and_store


class _StubTriage:
    def __init__(self, label_type: str = "Incident", priority: str = "high", conf: float = 0.9):
        self.label_type = label_type
        self.priority = priority
        self.conf = conf

    def predict(self, subject, body):
        def head(label, conf):
            return HeadPrediction(label=label, confidence=conf, probabilities={label: conf})

        return TriagePrediction(
            type=head(self.label_type, self.conf),
            queue=head("Technical Support", self.conf),
            priority=head(self.priority, self.conf),
            language="en",
            language_confidence=0.99,
        )


def _make_stub_agent(label_type: str = "Request", priority: str = "low", conf: float = 0.9) -> SentinelAgent:
    settings = Settings(llm_provider="extractive", llm_fallback="", warm_up=False)
    store = VectorStore(":memory:", HashEmbedder())
    row = pd.Series(
        {
            "ticket_id": "TKT-00001",
            "subject": "VPN down",
            "body": "VPN gateway refuses connections",
            "answer": "Restarted the VPN gateway and cleared stale sessions.",
            "type": "Incident",
            "queue": "Technical Support",
            "priority": "high",
            "language": "en",
        }
    )
    store.add([ticket_chunk(row)], embed_texts=["VPN down\nVPN gateway refuses connections"])
    return SentinelAgent(
        settings=settings,
        store=store,
        router=LLMRouter(settings),
        triage_model=_StubTriage(label_type=label_type, priority=priority, conf=conf),
    )


def _make_result(tier: str) -> SentinelResult:
    return SentinelResult(
        subject="Test",
        body="Body",
        detected_language="en",
        language_confidence=0.99,
        triage=TriageLabels(
            type="Incident",
            queue="Technical Support",
            priority="high",
            type_confidence=0.9,
            queue_confidence=0.85,
            priority_confidence=0.8,
            triage_confidence=0.8,
        ),
        escalation="AUTO_DRAFT" if tier == "AUTO_DRAFT" else "ESCALATE",
        tier=tier,  # type: ignore[arg-type]
    )


def test_group_tickets_by_tier_and_resolved():
    ticket_store.reset()
    t1 = ticket_store.add_ticket("Outage", "VPN down", source="preset")
    t2 = ticket_store.add_ticket("Unsure", "Maybe billing?", source="preset")
    t3 = ticket_store.add_ticket("Simple", "Reset password", source="preset")
    t4 = ticket_store.add_ticket("Done", "Already handled", source="preset")
    t5 = ticket_store.add_ticket("New", "Not triaged yet", source="customer")

    ticket_store.save_result(t1, _make_result("PAGE_ONCALL"))
    ticket_store.save_result(t2, _make_result("AGENT_REVIEW"))
    ticket_store.save_result(t3, _make_result("AUTO_DRAFT"))
    ticket_store.save_result(t4, _make_result("AUTO_DRAFT"))
    ticket_store.set_status(t4, "replied")

    grouped = group_tickets_by_tier(ticket_store.list_tickets())
    assert [r.ticket_id for r in grouped["PAGE_ONCALL"]] == [t1]
    assert [r.ticket_id for r in grouped["AGENT_REVIEW"]] == [t2]
    assert [r.ticket_id for r in grouped["AUTO_DRAFT"]] == [t3]
    assert [r.ticket_id for r in grouped["RESOLVED"]] == [t4]
    assert [r.ticket_id for r in grouped["PENDING"]] == [t5]
    ticket_store.reset()


def test_build_board_dataframe_columns_and_waiting_time():
    ticket_store.reset()
    tid = ticket_store.add_ticket("VPN down", "Gateway refuses connections", source="preset")
    ticket_store.save_result(tid, _make_result("PAGE_ONCALL"))
    recs = ticket_store.list_tickets()
    df = build_board_dataframe(recs, now=recs[0].created_at + 125)
    assert list(df.columns) == [
        "ticket_id",
        "ticket",
        "type",
        "team",
        "priority",
        "AI confidence",
        "waiting time",
    ]
    assert df.loc[0, "AI confidence"] == pytest.approx(0.8)
    assert df.loc[0, "waiting time"] == "2m"
    assert format_waiting_time(100, now=145) == "45s"
    assert format_waiting_time(0, now=3660) == "1h 1m"
    ticket_store.reset()


def test_triage_and_store_persists_tier():
    ticket_store.reset()
    agent = _make_stub_agent(label_type="Incident", priority="high", conf=0.9)
    tid, res = triage_and_store(agent, "VPN down", "VPN gateway refuses connections", source="preset")
    rec = ticket_store.get_ticket(tid)
    assert rec is not None
    assert rec.status == "triaged"
    assert res.tier == "PAGE_ONCALL"
    assert rec.result is not None and rec.result.tier == "PAGE_ONCALL"
    ticket_store.reset()


def test_agent_page_apptest_preset_populates_board_and_panel(monkeypatch):
    from streamlit.testing.v1 import AppTest

    ticket_store.reset()
    stub_agent = _make_stub_agent(label_type="Incident", priority="high", conf=0.9)
    monkeypatch.setattr("ui.shared.get_agent", lambda: stub_agent)

    agent_page = Path(__file__).resolve().parents[1] / "ui/pages/agent.py"
    at = AppTest.from_file(agent_page, default_timeout=15)
    at.run()
    assert not at.exception
    # Click the first preset button ("Critical outage (EN)")
    preset_btn = next(b for b in at.button if b.key == "preset_0")
    preset_btn.click().run()
    assert not at.exception

    tickets = ticket_store.list_tickets()
    assert len(tickets) == 1
    assert tickets[0].result is not None
    assert tickets[0].result.tier == "PAGE_ONCALL"
    # Verify panel sections rendered
    markdown_text = "\n".join(m.value for m in at.markdown)
    assert "Briefing" in markdown_text
    assert "Verdict & action" in markdown_text
    assert "Triage predictions & why" in markdown_text
    assert "Safety checks" in markdown_text
    assert "Drafted reply & citations" in markdown_text
    ticket_store.reset()
