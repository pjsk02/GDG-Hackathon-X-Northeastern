"""Tests for POST /triage role-based responses in api/main.py."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import main as api_main
from sentinel import ticket_store
from shared.contracts import Precedent, SentinelResult, TriageLabels, VerifiedCitation


class _FakeSentinelAgent:
    def __init__(self, result: SentinelResult):
        self._result = result

    def triage(self, subject, body, k=None, provider=None, fallback=True) -> SentinelResult:
        return self._result.model_copy(deep=True)


def _sample_result(*, tier: str = "AUTO_DRAFT", grounded: bool = True, draft_reply: str | None = "Restart VPN.") -> SentinelResult:
    return SentinelResult(
        subject="VPN issue",
        body="Cannot connect. Email: alice@example.com",
        detected_language="en",
        language_confidence=0.99,
        triage=TriageLabels(
            type="Request",
            queue="Technical Support",
            priority="low",
            type_confidence=0.92,
            queue_confidence=0.88,
            priority_confidence=0.90,
            triage_confidence=0.88,
        ),
        escalation="AUTO_DRAFT" if tier == "AUTO_DRAFT" else "ESCALATE",
        escalation_reasons=[] if tier == "AUTO_DRAFT" else ["R1 high-priority Incident: page the on-call engineer"],
        tier=tier,  # type: ignore[arg-type]
        pii_masked=True,
        pii_found={"email": 1},
        pii_masked_body="Cannot connect. Email: [EMAIL]",
        precedents=[
            Precedent(
                ticket_id="TKT-00001",
                similarity=0.91,
                subject="VPN",
                body_snippet="VPN issue",
                answer="Restart VPN.",
                type="Request",
                queue="Technical Support",
                priority="low",
                language="en",
            )
        ],
        top_similarity=0.91,
        draft_reply=draft_reply,
        cited_ticket_ids=["TKT-00001"] if grounded else [],
        verified_citations=[VerifiedCitation(ticket_id="TKT-00001", evidence_quote="Restart VPN.", similarity=0.91)]
        if grounded
        else [],
        grounded=grounded,
    )


def test_triage_customer_role_returns_only_status_and_approved_reply(monkeypatch):
    ticket_store.reset()
    monkeypatch.setattr(api_main, "get_sentinel_agent", lambda: _FakeSentinelAgent(_sample_result()))
    client = TestClient(api_main.app)

    resp = client.post("/triage", json={"subject": "VPN", "body": "Help"}, headers={"X-Role": "customer"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"ticket_id", "status", "reply"}
    assert data["status"] == "Replied"
    assert data["reply"] == "Restart VPN."
    ticket_store.reset()


def test_triage_customer_role_escalated_hides_draft_and_internal_fields(monkeypatch):
    ticket_store.reset()
    res = _sample_result(tier="PAGE_ONCALL", grounded=True, draft_reply="Internal notes only")
    monkeypatch.setattr(api_main, "get_sentinel_agent", lambda: _FakeSentinelAgent(res))
    client = TestClient(api_main.app)

    # Default (no X-Role header) also defaults to customer
    resp = client.post("/triage", json={"body": "Everything is down"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"ticket_id", "status", "reply"}
    assert data["status"] == "In progress"
    assert data["reply"] is None
    ticket_store.reset()


def test_triage_agent_and_manager_roles_receive_full_result(monkeypatch):
    ticket_store.reset()
    monkeypatch.setattr(api_main, "get_sentinel_agent", lambda: _FakeSentinelAgent(_sample_result()))
    client = TestClient(api_main.app)

    for role in ("agent", "manager"):
        resp = client.post("/triage", json={"body": "Help"}, headers={"X-Role": role})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "AUTO_DRAFT"
        assert data["triage"]["triage_confidence"] == 0.88
        assert len(data["precedents"]) == 1
        assert data["pii_masked_body"] == "Cannot connect. Email: [EMAIL]"
    ticket_store.reset()


def test_triage_invalid_role_returns_422(monkeypatch):
    monkeypatch.setattr(api_main, "get_sentinel_agent", lambda: _FakeSentinelAgent(_sample_result()))
    client = TestClient(api_main.app)
    resp = client.post("/triage", json={"body": "Help"}, headers={"X-Role": "admin"})
    assert resp.status_code == 422
