"""SmartQueue with a fake agent: urgent tickets jump ahead, the concurrency limit holds, statuses move."""

import threading
import time
from types import SimpleNamespace

import pytest

from sentinel import ticket_store
from sentinel.smart_queue import DEFAULT_RANK, QueueStats, SmartQueue, rank_for
from shared.contracts import SentinelResult, TriageLabels


def _labels(subject, body):
    text = f"{subject or ''} {body}".lower()
    if "outage" in text or "down" in text or "vpn" in text:
        return "Incident", "high"
    if "refund" in text:
        return "Request", "high"
    if "minor" in text:
        return "Request", "low"
    return "Request", "medium"


class FakeModel:
    def predict(self, subject, body):
        t, p = _labels(subject, body)
        return SimpleNamespace(type=SimpleNamespace(label=t), priority=SimpleNamespace(label=p))


class FakeAgent:
    """Sleeps `delay` per ticket; records order and peak concurrency. `gate` (Event) holds every call until set."""

    def __init__(self, delay=0.01, gate=None, fail_on=None):
        self.triage_model = FakeModel()
        self.delay, self.gate, self.fail_on = delay, gate, fail_on
        self.order: list[str] = []
        self.active = self.peak = 0
        self._lock = threading.Lock()

    def triage(self, subject, body):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if self.gate is not None:
                self.gate.wait(5)
            time.sleep(self.delay)
            if self.fail_on and self.fail_on in body:
                raise RuntimeError("boom")
            t, p = _labels(subject, body)
            with self._lock:
                self.order.append(body)
            return SentinelResult(
                subject=subject, body=body, detected_language="en", language_confidence=1.0,
                triage=TriageLabels(type=t, queue="IT", priority=p, type_confidence=1, queue_confidence=1,
                                    priority_confidence=1, triage_confidence=1),
                escalation="AUTO_DRAFT",
            )
        finally:
            with self._lock:
                self.active -= 1


@pytest.fixture(autouse=True)
def store(tmp_path):
    ticket_store.configure(tmp_path / "tickets.sqlite")
    yield
    ticket_store.configure(None)


@pytest.fixture
def queues():
    made: list[SmartQueue] = []
    yield made
    for q in made:
        q.shutdown(timeout=5)


def _queue(queues, agent, **kw) -> SmartQueue:
    q = SmartQueue(agent, **kw)
    queues.append(q)
    return q


def _add(*bodies):
    return [ticket_store.add_ticket(None, b, source="simulator") for b in bodies]


def test_rank_for():
    assert rank_for("Incident", "high") == 0
    assert rank_for("Problem", "high") == 0
    assert rank_for("Request", "high") == 1
    assert rank_for("Incident", "medium") == 2
    assert rank_for("Change", "low") == 3
    assert rank_for("Request", "unknown") == DEFAULT_RANK


def test_burst_runs_in_urgency_order(queues):
    agent = FakeAgent()
    q = _queue(queues, agent, concurrency=1)
    _add_ids = _add("a minor thing", "routine question", "refund please", "VPN outage", "another routine", "API down")
    q.submit_many(_add_ids)
    assert q.wait_idle(5)
    assert agent.order == ["VPN outage", "API down", "refund please", "routine question", "another routine",
                           "a minor thing"]


def test_urgent_ticket_jumps_ahead_of_waiting_ones(queues):
    gate = threading.Event()
    agent = FakeAgent(gate=gate)
    q = _queue(queues, agent, concurrency=1)
    first, routine1, routine2 = _add("routine 1", "routine 2", "routine 3")
    q.submit(first)
    _wait_for(lambda: q.snapshot()["processing"] == [first])
    q.submit(routine1)
    q.submit(routine2)
    (urgent,) = _add("VPN outage for everyone")
    q.submit(urgent)
    assert q.snapshot()["waiting"] == [urgent, routine1, routine2]
    gate.set()
    assert q.wait_idle(5)
    assert agent.order == ["routine 1", "VPN outage for everyone", "routine 2", "routine 3"]


def test_concurrency_limit_is_respected(queues):
    agent = FakeAgent(delay=0.03)
    q = _queue(queues, agent, concurrency=3)
    q.submit_many(_add(*[f"routine {i}" for i in range(12)]))
    assert q.wait_idle(10)
    assert agent.peak == 3
    assert q.stats().done == 12


def test_set_concurrency_takes_effect(queues):
    agent = FakeAgent(delay=0.03)
    q = _queue(queues, agent, concurrency=1)
    q.submit_many(_add(*[f"routine {i}" for i in range(3)]))
    assert q.wait_idle(5)
    assert agent.peak == 1
    q.set_concurrency(4)
    q.submit_many(_add(*[f"routine {i}" for i in range(8)]))
    assert q.wait_idle(5)
    assert agent.peak == 4
    q.set_concurrency(2)
    agent.peak = 0
    q.submit_many(_add(*[f"routine {i}" for i in range(8)]))
    assert q.wait_idle(5)
    assert agent.peak == 2  # extra worker threads stay idle
    assert q.stats().concurrency == 2


def test_statuses_and_live_numbers(queues):
    gate = threading.Event()
    agent = FakeAgent(gate=gate)
    q = _queue(queues, agent, concurrency=2)
    ids = _add("VPN outage", "routine 1", "routine 2", "routine 3")
    q.submit_many(ids)
    _wait_for(lambda: len(q.snapshot()["processing"]) == 2)
    statuses = {tid: ticket_store.get_ticket(tid).status for tid in ids}
    assert sorted(statuses.values()) == ["processing", "processing", "queued", "queued"]
    assert statuses[ids[0]] == "processing"  # the urgent one started first
    s = q.stats()
    assert (s.waiting, s.processing, s.done, s.concurrency) == (2, 2, 0, 2)
    assert q.fast_triage[ids[0]] == {"type": "Incident", "priority": "high", "rank": 0}
    gate.set()
    assert q.wait_idle(5)
    assert all(ticket_store.get_ticket(t).status == "triaged" for t in ids)
    assert ticket_store.get_ticket(ids[0]).result.triage.type == "Incident"
    snap = q.snapshot()
    assert snap["waiting"] == [] and snap["processing"] == [] and sorted(snap["done"]) == sorted(ids)
    s = q.stats()
    assert isinstance(s, QueueStats) and s.done == 4 and s.throughput_per_min > 0


def test_failed_ticket_does_not_stop_the_queue(queues):
    agent = FakeAgent(fail_on="explode")
    q = _queue(queues, agent, concurrency=1)
    bad, good = _add("please explode", "routine")
    q.submit_many([bad, good])
    assert q.wait_idle(5)
    assert q.snapshot()["failed"] == [bad] and q.snapshot()["done"] == [good]
    assert ticket_store.get_ticket(bad).status == "new"
    assert ticket_store.get_ticket(good).status == "triaged"
    assert q.stats().failed == 1


def test_on_result_callback(queues):
    seen = []
    q = _queue(queues, FakeAgent(), concurrency=2, on_result=lambda tid, r: seen.append((tid, r.triage.type)))
    ids = _add("VPN outage", "routine")
    q.submit_many(ids)
    assert q.wait_idle(5)
    assert sorted(seen) == sorted([(ids[0], "Incident"), (ids[1], "Request")])


def test_fast_model_failure_uses_default_rank(queues):
    agent = FakeAgent()
    agent.triage_model = SimpleNamespace(predict=lambda s, b: (_ for _ in ()).throw(RuntimeError("no model")))
    q = _queue(queues, agent, concurrency=1)
    (tid,) = _add("routine")
    q.submit(tid)
    assert q.wait_idle(5)
    assert q.fast_triage[tid]["rank"] == DEFAULT_RANK
    assert ticket_store.get_ticket(tid).status == "triaged"


def test_unknown_ticket_and_shutdown(queues):
    q = _queue(queues, FakeAgent(), concurrency=2)
    with pytest.raises(KeyError):
        q.submit("SD-9999")
    q.shutdown(timeout=5)
    assert all(not t.is_alive() for t in q._workers)
    (tid,) = _add("routine")
    with pytest.raises(RuntimeError):
        q.submit(tid)


def test_shutdown_leaves_waiting_tickets_queued(queues):
    gate = threading.Event()
    q = _queue(queues, FakeAgent(gate=gate), concurrency=1)
    running, waiting = _add("routine 1", "routine 2")
    q.submit_many([running, waiting])
    _wait_for(lambda: q.snapshot()["processing"] == [running])
    stopper = threading.Thread(target=q.shutdown, kwargs={"timeout": 5})
    stopper.start()
    gate.set()
    stopper.join(5)
    assert ticket_store.get_ticket(running).status == "triaged"
    assert ticket_store.get_ticket(waiting).status == "queued"


def _wait_for(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.005)
