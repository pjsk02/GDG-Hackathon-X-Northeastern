"""Tests for Step 3: Customer page status mapping and submission flow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from agent.llm_router import LLMRouter
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from sentinel import ticket_store
from sentinel.ingest_tickets import ticket_chunk
from sentinel.pipeline import SentinelAgent
from sentinel.triage import HeadPrediction, TriagePrediction
from shared.settings import Settings
from ui.shared import customer_status_label


class _StubTriage:
    def predict(self, subject, body):
        def head(label, conf):
            return HeadPrediction(label=label, confidence=conf, probabilities={label: conf})

        return TriagePrediction(
            type=head("Incident", 0.9),
            queue=head("Technical Support", 0.85),
            priority=head("high", 0.9),
            language="en",
            language_confidence=0.99,
        )


def _make_stub_agent() -> SentinelAgent:
    settings = Settings(llm_provider="extractive", llm_fallback="", warm_up=False)
    store = VectorStore(":memory:", HashEmbedder())
    row = pd.Series(
        {
            "ticket_id": "TKT-00001",
            "subject": "Login",
            "body": "Cannot login",
            "answer": "Cleared SSO cache and reset token.",
            "type": "Incident",
            "queue": "Technical Support",
            "priority": "high",
            "language": "en",
        }
    )
    store.add([ticket_chunk(row)], embed_texts=["Login\nCannot login"])
    return SentinelAgent(settings=settings, store=store, router=LLMRouter(settings), triage_model=_StubTriage())


def test_customer_status_label_mapping():
    for raw in ("new", "queued", "processing"):
        assert customer_status_label(raw) == "Received"
    assert customer_status_label("triaged") == "In progress"
    for raw in ("replied", "closed"):
        assert customer_status_label(raw) == "Replied"


def test_customer_page_submits_ticket_and_hides_internal_fields(monkeypatch):
    from streamlit.testing.v1 import AppTest

    ticket_store.reset()
    stub_agent = _make_stub_agent()
    monkeypatch.setattr("ui.shared.get_agent", lambda: stub_agent)

    customer_page = Path(__file__).resolve().parents[1] / "ui/pages/customer.py"
    at = AppTest.from_file(customer_page, default_timeout=15)
    at.run()
    assert not at.exception

    # Leave subject empty (optional) and submit body with an email (PII)
    at.text_area[0].set_value("Cannot log in, contact me at secret.user@example.com")
    at.button[0].click().run()
    assert not at.exception

    tickets = ticket_store.list_tickets()
    assert len(tickets) == 1
    assert tickets[0].source == "customer"

    rendered = "\n".join(m.value for m in at.markdown)
    assert tickets[0].ticket_id in rendered
    assert "In progress" in rendered
    # Customers must never see internal fields
    assert "PAGE_ONCALL" not in rendered
    assert "TKT-00001" not in rendered
    assert "[EMAIL]" not in rendered
    assert "R1" not in rendered
    ticket_store.reset()
