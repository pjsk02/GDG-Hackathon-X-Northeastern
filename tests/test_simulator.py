"""Demo burst: the right mix of tickets, and fire() stores and submits them."""

import pytest

from sentinel import simulator, ticket_store
from sentinel.smart_queue import SmartQueue
from tests.test_smart_queue import FakeAgent


@pytest.fixture(autouse=True)
def store(tmp_path):
    ticket_store.configure(tmp_path / "tickets.sqlite")
    yield
    ticket_store.configure(None)


def test_demo_ticket_mix():
    kinds = [t["kind"] for t in simulator.DEMO_TICKETS]
    assert len(kinds) == 10
    outages = [t for t in simulator.DEMO_TICKETS if t["kind"].startswith("outage")]
    assert len(outages) == 3 and all("vpn" in (t["subject"] + t["body"]).lower() for t in outages)
    assert kinds.count("refund_trap") == 1
    assert sum(k.endswith("_de") for k in kinds) >= 2
    assert kinds[0] == "routine"  # routine first, so the reordering is visible


def test_fire_adds_and_submits_as_one_burst():
    agent = FakeAgent()
    q = SmartQueue(agent, concurrency=1)
    try:
        ids = simulator.fire(q, n=10)
        assert len(ids) == 10
        assert all(ticket_store.get_ticket(t).source == "simulator" for t in ids)
        assert q.wait_idle(10)
        assert all(ticket_store.get_ticket(t).status == "triaged" for t in ids)
        # FakeAgent ranks VPN/outage tickets as high Incidents: all three finish first although they arrived
        # 3rd, 5th and 6th, behind routine tickets.
        kind_of = {t["body"]: t["kind"] for t in simulator.DEMO_TICKETS}
        assert [kind_of[b] for b in agent.order[:3]] == ["outage", "outage", "outage_de"]
    finally:
        q.shutdown(timeout=5)


def test_fire_with_a_contract_only_queue():
    submitted = []

    class PlainQueue:
        def submit(self, ticket_id):
            submitted.append(ticket_id)

    ids = simulator.fire(PlainQueue(), n=3)
    assert submitted == ids and len(ids) == 3
