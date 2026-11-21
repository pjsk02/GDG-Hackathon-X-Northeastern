"""Smart priority queue in front of the pipeline (N5). File name avoids shadowing the stdlib `queue`.

Owner: C (Rithwik). STUB: processes tickets one at a time, in arrival order, on the caller's
thread. C replaces it with: classify on arrival, high-priority Incidents jump the line, at most
settings.queue_concurrency tickets in the LLM step at once, background worker threads.
The queue page (owner E) uses exactly this interface; keep it stable.

    q = SmartQueue(agent, concurrency=4)
    q.submit(ticket_id)            # ticket already in sentinel.ticket_store
    q.stats() -> QueueStats        # live numbers for the UI
    q.snapshot() -> dict           # {"waiting": [ids in run order], "processing": [ids], "done": [ids]}
    q.set_concurrency(n)
    q.shutdown()
"""

from __future__ import annotations

import time

from pydantic import BaseModel

from sentinel import ticket_store


class QueueStats(BaseModel):
    waiting: int = 0
    processing: int = 0
    done: int = 0
    concurrency: int = 1
    throughput_per_min: float = 0.0


class SmartQueue:
    def __init__(self, agent, concurrency: int = 4) -> None:
        self.agent = agent
        self.concurrency = concurrency
        self._done: list[str] = []
        self._started = time.time()

    def submit(self, ticket_id: str) -> None:
        rec = ticket_store.get_ticket(ticket_id)
        if rec is None:
            raise KeyError(ticket_id)
        ticket_store.set_status(ticket_id, "processing")
        result = self.agent.triage(rec.subject, rec.body)
        ticket_store.save_result(ticket_id, result)
        self._done.append(ticket_id)

    def stats(self) -> QueueStats:
        minutes = max((time.time() - self._started) / 60, 1e-9)
        return QueueStats(done=len(self._done), concurrency=self.concurrency,
                          throughput_per_min=round(len(self._done) / minutes, 1))

    def snapshot(self) -> dict:
        return {"waiting": [], "processing": [], "done": list(self._done)}

    def set_concurrency(self, n: int) -> None:
        self.concurrency = max(1, int(n))

    def shutdown(self) -> None:
        pass
