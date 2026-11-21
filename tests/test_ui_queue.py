"""Tests for Step 5: Smart queue page, burst firing, and Major Incident outage banner."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from agent.llm_router import LLMRouter
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from sentinel import ticket_store
from sentinel.ingest_tickets import ticket_chunk
from sentinel.outage import OutageTracker
from sentinel.pipeline import SentinelAgent
from sentinel.smart_queue import SmartQueue
from sentinel.triage import HeadPrediction, TriagePrediction
from shared.settings import Settings
from ui.shared import fire_burst


class _BurstTriage:
    def predict(self, subject, body):
        is_vpn = "vpn" in ((subject or "") + " " + body).lower()

        def head(label, conf):
            return HeadPrediction(label=label, confidence=conf, probabilities={label: conf})

        return TriagePrediction(
            type=head("Incident" if is_vpn else "Request", 0.9),
            queue=head("Technical Support", 0.85),
            priority=head("high" if is_vpn else "low", 0.9),
            language="en",
            language_confidence=0.99,
        )


def _make_burst_agent() -> SentinelAgent:
    settings = Settings(llm_provider="extractive", llm_fallback="", warm_up=False)
    store = VectorStore(":memory:", HashEmbedder())
    row = pd.Series(
        {
            "ticket_id": "TKT-00001",
            "subject": "VPN gateway down",
            "body": "VPN gateway refuses all connections",
            "answer": "Restarted the VPN gateway and cleared stale sessions.",
            "type": "Incident",
            "queue": "Technical Support",
            "priority": "high",
            "language": "en",
        }
    )
    store.add([ticket_chunk(row)], embed_texts=["VPN gateway down\nVPN gateway refuses all connections"])
    return SentinelAgent(settings=settings, store=store, router=LLMRouter(settings), triage_model=_BurstTriage())


def test_fire_burst_and_outage_banner_raises_alert():
    ticket_store.reset()
    agent = _make_burst_agent()
    q = SmartQueue(agent, concurrency=2)
    fired = fire_burst(q)
    assert fired == 10
    assert q.wait_idle(timeout=30)  # the real SmartQueue works in background threads
    assert q.stats().done == 10

    tracker = OutageTracker()
    for tid in q.snapshot()["done"]:
        rec = ticket_store.get_ticket(tid)
        assert rec is not None and rec.result is not None
        tracker.observe(rec.result)

    alert = tracker.check()
    assert alert is not None
    assert "MAJOR INCIDENT" in alert.headline
    ticket_store.reset()


def test_queue_page_apptest_fire_10_and_concurrency_and_group_burst(monkeypatch):
    from streamlit.testing.v1 import AppTest

    ticket_store.reset()
    agent = _make_burst_agent()
    q = SmartQueue(agent, concurrency=2)
    monkeypatch.setattr("ui.shared.get_agent", lambda: agent)
    monkeypatch.setattr("ui.shared.get_queue", lambda _a: q)

    queue_page = Path(__file__).resolve().parents[1] / "ui/pages/queue.py"
    at = AppTest.from_file(queue_page, default_timeout=15)
    at.run()
    assert not at.exception

    # Adjust concurrency slider
    slider = next(s for s in at.slider if s.key == "queue_concurrency_slider")
    slider.set_value(5).run()
    assert q.concurrency == 5

    # Click Fire 10 tickets
    fire_btn = next(b for b in at.button if b.key == "fire_10_btn")
    fire_btn.click().run()
    assert not at.exception
    assert q.wait_idle(timeout=30)  # background workers finish the burst
    at.run()  # AppTest does not run the 1 s live fragment; re-render so the banner sees the done tickets
    assert not at.exception
    assert q.stats().done == 10

    # Banner should now be visible with "Group into one incident" button
    group_btn = next(b for b in at.button if b.key == "queue_group_burst")
    group_btn.click().run()
    assert not at.exception
    # Rithwik's real sentinel.incidents.group_burst(alert, tickets) grouped the burst
    # (only the VPN outage tickets of the mixed burst belong to the incident)
    assert any(s.value.startswith("Grouped ") and "INC-" in s.value and "VPN outage" in s.value for s in at.success)
    ticket_store.reset()
