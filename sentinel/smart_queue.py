"""Smart priority queue in front of the pipeline (N5). File name avoids shadowing the stdlib `queue`.

Owner: C (Rithwik). The queue page (owner E) uses exactly this interface; keep it stable.

    q = SmartQueue(agent, concurrency=4)
    q.submit(ticket_id)            # ticket already in sentinel.ticket_store
    q.stats() -> QueueStats        # live numbers for the UI
    q.snapshot() -> dict           # {"waiting": [ids in run order], "processing": [ids], "done": [ids]}
    q.set_concurrency(n)
    q.shutdown()

How it works:
- `submit` classifies the ticket at once with the fast triage model (`agent.triage_model.predict`, ~1 ms) and gives
  it a rank: high-priority Incident/Problem 0, other high 1, medium 2, low 3. Equal ranks run in arrival order.
- Background worker threads run the full `agent.triage` with at most `concurrency` tickets at once, moving the
  ticket's status queued -> processing -> triaged in the ticket store.
- `set_concurrency` takes effect when the next ticket is picked. `shutdown` stops the workers after the tickets
  they are running; tickets still waiting stay "queued".
- Extras (not part of the frozen contract): `submit_many(ids)` for bursts, `on_result(ticket_id, result)` callback
  (e.g. OutageTracker.observe), `fast_triage[ticket_id]` with the arrival labels, `wait_idle(timeout)`, a "failed"
  list in `snapshot()` and `failed` in `stats()`.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
import time
from collections.abc import Callable

from pydantic import BaseModel

from sentinel import ticket_store

log = logging.getLogger(__name__)

URGENT_TYPES = {"Incident", "Problem"}
PRIORITY_RANK = {"high": 1, "medium": 2, "low": 3}
DEFAULT_RANK = 2  # unknown priority, or the fast model is unavailable


class QueueStats(BaseModel):
    waiting: int = 0
    processing: int = 0
    done: int = 0
    concurrency: int = 1
    throughput_per_min: float = 0.0
    failed: int = 0


def rank_for(ticket_type: str, priority: str) -> int:
    """0 runs first. High-priority incidents jump everything, then plain priority order."""
    if priority == "high" and ticket_type in URGENT_TYPES:
        return 0
    return PRIORITY_RANK.get(priority, DEFAULT_RANK)


class SmartQueue:
    def __init__(
        self, agent, concurrency: int = 4, on_result: Callable[[str, object], None] | None = None
    ) -> None:
        self.agent = agent
        self.concurrency = max(1, int(concurrency))
        self.on_result = on_result
        self.fast_triage: dict[str, dict] = {}
        self._cond = threading.Condition()
        self._heap: list[tuple[int, int, str]] = []
        self._seq = itertools.count()
        self._processing: list[str] = []
        self._done: list[str] = []
        self._failed: list[str] = []
        self._first_submit: float | None = None
        self._stopping = False
        self._workers: list[threading.Thread] = []
        self._ensure_workers()

    # -- contract ------------------------------------------------------------

    def submit(self, ticket_id: str) -> None:
        self.submit_many([ticket_id])

    def submit_many(self, ticket_ids: list[str]) -> None:
        """Classify every ticket first, then queue them in one go, so a burst is ordered by urgency
        (one-by-one submits let the first tickets start before the urgent ones have arrived)."""
        ranked = []
        for ticket_id in ticket_ids:
            rec = ticket_store.get_ticket(ticket_id)
            if rec is None:
                raise KeyError(ticket_id)
            ranked.append((ticket_id, *self._classify(rec.subject, rec.body)))
        with self._cond:
            if self._stopping:
                raise RuntimeError("queue is shut down")
            for ticket_id, rank, labels in ranked:
                ticket_store.set_status(ticket_id, "queued")
                self.fast_triage[ticket_id] = {**labels, "rank": rank}
                heapq.heappush(self._heap, (rank, next(self._seq), ticket_id))
            if self._first_submit is None:
                self._first_submit = time.time()
            self._cond.notify_all()

    def stats(self) -> QueueStats:
        with self._cond:
            done = len(self._done)
            minutes = (time.time() - self._first_submit) / 60 if self._first_submit else 0.0
            return QueueStats(
                waiting=len(self._heap), processing=len(self._processing), done=done,
                concurrency=self.concurrency, failed=len(self._failed),
                throughput_per_min=round(done / minutes, 1) if minutes > 0 else 0.0,
            )

    def snapshot(self) -> dict:
        with self._cond:
            return {
                "waiting": [tid for _, _, tid in sorted(self._heap)],
                "processing": list(self._processing),
                "done": list(self._done),
                "failed": list(self._failed),
            }

    def set_concurrency(self, n: int) -> None:
        with self._cond:
            self.concurrency = max(1, int(n))
            self._ensure_workers()
            self._cond.notify_all()

    def shutdown(self, timeout: float | None = 30.0) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
            workers = list(self._workers)
        for t in workers:
            t.join(timeout)

    # -- extras --------------------------------------------------------------

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until nothing is waiting or processing. False on timeout."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while self._heap or self._processing:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    # -- internals -----------------------------------------------------------

    def _classify(self, subject: str | None, body: str) -> tuple[int, dict]:
        try:
            pred = self.agent.triage_model.predict(subject, body)
        except Exception:  # a missing model must not stop tickets from being queued
            log.exception("fast triage failed; queueing with default rank")
            return DEFAULT_RANK, {"type": "", "priority": ""}
        labels = {"type": pred.type.label, "priority": pred.priority.label}
        return rank_for(labels["type"], labels["priority"]), labels

    def _ensure_workers(self) -> None:
        # Threads only grow: lowering concurrency leaves extra workers idle (they wait for a free slot).
        while len(self._workers) < self.concurrency:
            t = threading.Thread(target=self._work, name=f"smart-queue-{len(self._workers)}", daemon=True)
            self._workers.append(t)
            t.start()

    def _work(self) -> None:
        while True:
            with self._cond:
                while not self._stopping and (not self._heap or len(self._processing) >= self.concurrency):
                    self._cond.wait()
                if self._stopping:
                    return
                _, _, ticket_id = heapq.heappop(self._heap)
                self._processing.append(ticket_id)
            ok = self._process(ticket_id)
            with self._cond:
                self._processing.remove(ticket_id)
                (self._done if ok else self._failed).append(ticket_id)
                self._cond.notify_all()

    def _process(self, ticket_id: str) -> bool:
        try:
            rec = ticket_store.get_ticket(ticket_id)
            if rec is None:
                raise KeyError(ticket_id)
            ticket_store.set_status(ticket_id, "processing")
            result = self.agent.triage(rec.subject, rec.body)
            ticket_store.save_result(ticket_id, result)
        except Exception:
            log.exception("triage failed for %s", ticket_id)
            try:
                ticket_store.set_status(ticket_id, "new")  # visible as not done; can be resubmitted
            except Exception:
                pass
            return False
        if self.on_result is not None:
            try:
                self.on_result(ticket_id, result)
            except Exception:
                log.exception("on_result callback failed for %s", ticket_id)
        return True
