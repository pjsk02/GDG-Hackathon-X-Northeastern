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


def _sample_result(*, tier: str = "AUTO_DRAFT", ticket_type: str = "Request", grounded: bool = True, draft_reply: str | None = "Restart VPN.") -> SentinelResult:
    return SentinelResult(
        subject="VPN issue",
        body="Cannot connect. Email: alice@example.com",
        detected_language="en",
        language_confidence=0.99,
        triage=TriageLabels(
            type=ticket_type,
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


def test_tickets_list_action_and_outage_endpoints(monkeypatch):
    ticket_store.reset()
    api_main._OUTAGE_TRACKER.reset()
    monkeypatch.setattr(api_main, "get_sentinel_agent", lambda: _FakeSentinelAgent(_sample_result(tier="PAGE_ONCALL", ticket_type="Incident")))
    client = TestClient(api_main.app)

    # Submit 3 matching outage tickets as customer
    for _ in range(3):
        r = client.post("/triage", json={"subject": "VPN down", "body": "VPN refuses"}, headers={"X-Role": "customer"})
        assert r.status_code == 200

    # Customer list hides internal fields
    cust_list = client.get("/tickets", headers={"X-Role": "customer"}).json()
    assert len(cust_list) == 3
    assert "triage" not in cust_list[0]
    assert cust_list[0]["status"] == "In progress"

    # Agent list includes full result
    agent_list = client.get("/tickets", headers={"X-Role": "agent"}).json()
    assert len(agent_list) == 3
    assert agent_list[0]["result"]["tier"] == "PAGE_ONCALL"

    # Outage endpoint reports active burst
    outage = client.get("/outage").json()
    assert outage["active"] is True
    assert outage["ticket_count"] == 3

    # Action endpoint closes ticket
    tid = agent_list[0]["ticket_id"]
    act = client.post(f"/tickets/{tid}/action", json={"status": "closed"}).json()
    assert act["status"] == "closed"

    # /desk, /user, /admin serve the live frontend HTML
    assert client.get("/desk").status_code == 200
    assert client.get("/user").status_code == 200
    assert client.get("/admin").status_code == 200
    ticket_store.reset()
    api_main._OUTAGE_TRACKER.reset()


def test_rbac_signup_signin_and_role_enforcement(monkeypatch):
    from api import auth as api_auth

    api_auth.reset_users()
    ticket_store.reset()
    monkeypatch.setattr(api_main, "get_sentinel_agent", lambda: _FakeSentinelAgent(_sample_result(tier="PAGE_ONCALL")))
    client = TestClient(api_main.app)

    # Sign up as user
    up_user = client.post(
        "/auth/signup",
        json={"name": "Alice", "email": "alice@clinic.org", "password": "secret", "role": "user"},
    )
    assert up_user.status_code == 200
    user_token = up_user.json()["token"]
    assert up_user.json()["user"]["role"] == "user"

    # Sign in with wrong password fails
    assert client.post("/auth/signin", json={"email": "alice@clinic.org", "password": "wrong"}).status_code == 401

    # Sign up as admin
    up_admin = client.post(
        "/auth/signup",
        json={"name": "Bob", "email": "bob@clinic.org", "password": "secret", "role": "admin"},
    )
    assert up_admin.status_code == 200
    admin_token = up_admin.json()["token"]

    # User token on /triage returns customer-filtered response even if X-Role: agent is spoofed
    t_resp = client.post(
        "/triage",
        json={"body": "VPN down"},
        headers={"Authorization": f"Bearer {user_token}", "X-Role": "agent"},
    )
    assert t_resp.status_code == 200
    assert set(t_resp.json().keys()) == {"ticket_id", "status", "reply"}
    tid = t_resp.json()["ticket_id"]

    # User token is blocked (403) from admin-only endpoints
    assert client.post(f"/tickets/{tid}/action", json={"status": "closed"}, headers={"Authorization": f"Bearer {user_token}"}).status_code == 403
    assert client.get("/outage", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403

    # Admin token can resolve ticket and check outage
    assert client.post(f"/tickets/{tid}/action", json={"status": "closed"}, headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
    assert client.get("/outage", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"}).json()["role"] == "admin"

    api_auth.reset_users()
    ticket_store.reset()
