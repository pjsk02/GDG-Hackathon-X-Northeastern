"""SQLite ticket store: add, list by status, save_result, set_status, persistence, concurrent writes."""

import threading

import pytest

from sentinel import ticket_store
from sentinel.ticket_store import TicketStore
from shared.contracts import GuardFinding, SentinelResult, TriageLabels


def _result(body: str = "VPN is down") -> SentinelResult:
    return SentinelResult(
        subject="VPN",
        body=body,
        detected_language="en",
        language_confidence=0.99,
        triage=TriageLabels(
            type="Incident", queue="Technical Support", priority="high",
            type_confidence=0.9, queue_confidence=0.8, priority_confidence=0.7, triage_confidence=0.7,
            queue_probabilities={"Technical Support": 0.8, "IT Support": 0.2},
        ),
        escalation="ESCALATE",
        escalation_reasons=["R1 high priority incident"],
        tier="PAGE_ONCALL",
        explanations={"type": ["vpn", "down"]},
        guard_findings=[GuardFinding(kind="number", text="48 hours", reason="not found in any verified quote")],
        cited_ticket_ids=["TKT-00042"],
    )


@pytest.fixture
def store(tmp_path):
    s = TicketStore(tmp_path / "tickets.sqlite")
    yield s
    s.close()


def test_add_and_get(store):
    tid = store.add_ticket("VPN", "VPN is down", source="simulator")
    assert tid == "SD-1001"
    rec = store.get_ticket(tid)
    assert (rec.subject, rec.body, rec.source, rec.status, rec.result) == ("VPN", "VPN is down", "simulator", "new", None)
    assert store.add_ticket(None, "second") == "SD-1002"
    assert store.get_ticket("SD-1002").subject is None
    assert store.get_ticket("SD-9999") is None


def test_empty_subject_is_stored_as_none(store):
    assert store.get_ticket(store.add_ticket("", "body")).subject is None


def test_list_newest_first_and_by_status(store):
    a, b, c = (store.add_ticket(None, f"t{i}") for i in range(3))
    assert [r.ticket_id for r in store.list_tickets()] == [c, b, a]
    store.set_status(a, "queued")
    store.set_status(c, "queued")
    assert [r.ticket_id for r in store.list_tickets("queued")] == [c, a]
    assert [r.ticket_id for r in store.list_tickets("new")] == [b]
    assert store.list_tickets("closed") == []


def test_set_status_validates_and_updates(store):
    tid = store.add_ticket(None, "x")
    before = store.get_ticket(tid).updated_at
    store.set_status(tid, "processing")
    rec = store.get_ticket(tid)
    assert rec.status == "processing" and rec.updated_at >= before
    with pytest.raises(ValueError):
        store.set_status(tid, "lost")
    with pytest.raises(KeyError):
        store.set_status("SD-9999", "queued")


def test_save_result_round_trips_and_sets_triaged(store):
    tid = store.add_ticket("VPN", "VPN is down")
    store.set_status(tid, "processing")
    result = _result()
    store.save_result(tid, result)
    rec = store.get_ticket(tid)
    assert rec.status == "triaged"
    assert rec.result == result
    assert rec.result.guard_findings[0].text == "48 hours"
    with pytest.raises(KeyError):
        store.save_result("SD-9999", result)


def test_persists_across_two_store_instances(tmp_path):
    path = tmp_path / "tickets.sqlite"
    first = TicketStore(path)
    tid = first.add_ticket("VPN", "VPN is down")
    first.save_result(tid, _result())
    first.close()

    second = TicketStore(path)
    rec = second.get_ticket(tid)
    assert rec.status == "triaged" and rec.result.tier == "PAGE_ONCALL"
    assert second.add_ticket(None, "next") == "SD-1002"  # ids continue, never reused
    second.close()


def test_two_open_instances_see_each_others_writes(tmp_path):
    a, b = TicketStore(tmp_path / "t.sqlite"), TicketStore(tmp_path / "t.sqlite")
    tid = a.add_ticket(None, "from a")
    b.set_status(tid, "queued")
    assert a.get_ticket(tid).status == "queued"
    a.close(), b.close()


def test_reset_clears_and_restarts_ids(store):
    store.add_ticket(None, "x")
    store.add_ticket(None, "y")
    store.reset()
    assert store.list_tickets() == []
    assert store.add_ticket(None, "z") == "SD-1001"


def test_concurrent_writes_from_threads(store):
    n_threads, per_thread = 8, 25
    ids: list[str] = []
    ids_lock = threading.Lock()
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(per_thread):
                tid = store.add_ticket(None, f"worker {n} ticket {i}", source="simulator")
                store.set_status(tid, "queued")
                store.set_status(tid, "processing")
                store.save_result(tid, _result(f"worker {n} ticket {i}"))
                with ids_lock:
                    ids.append(tid)
        except BaseException as e:  # surface thread failures in the test
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    total = n_threads * per_thread
    assert len(set(ids)) == total
    triaged = store.list_tickets("triaged")
    assert len(triaged) == total
    assert all(r.result.body == r.body for r in triaged)


def test_concurrent_writes_from_two_instances(tmp_path):
    path = tmp_path / "t.sqlite"
    stores = [TicketStore(path), TicketStore(path)]

    def worker(s: TicketStore) -> None:
        for i in range(30):
            s.set_status(s.add_ticket(None, f"t{i}"), "queued")

    threads = [threading.Thread(target=worker, args=(s,)) for s in stores]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({r.ticket_id for r in stores[0].list_tickets("queued")}) == 60
    for s in stores:
        s.close()


def test_module_functions_use_configured_path(tmp_path):
    path = tmp_path / "configured.sqlite"
    ticket_store.configure(path)
    try:
        ticket_store.reset()
        tid = ticket_store.add_ticket(None, "VPN is down", source="preset")
        ticket_store.set_status(tid, "queued")
        ticket_store.save_result(tid, _result())
        assert [r.ticket_id for r in ticket_store.list_tickets("triaged")] == [tid]
        assert TicketStore(path).get_ticket(tid).status == "triaged"
    finally:
        ticket_store.configure(None)


def test_module_default_under_pytest_is_not_the_demo_store():
    ticket_store.configure(None)
    assert ticket_store._get_store().path != ticket_store.get_settings().ticket_store_path
