"""Why-this-label explanations (N3).

Owner: B (Shishir). STUB: returns {} until implemented. sentinel/pipeline.py already calls it.

Contract (keep stable):
    explain(model: TriageModel, text: str, top_n: int = 3) -> dict[str, list[str]]
    -> {"type": ["bricht ständig ab", ...], "queue": [...], "priority": [...]}

Return short, human-readable word n-grams that pushed the PREDICTED class of each head
(e.g. coefficient x tf-idf value of the word-level features). Skip character n-grams; agents
cannot read "rbin". Must run in a few milliseconds and never raise for normal input.
"""

from __future__ import annotations

from typing import Any


def explain(model: Any, text: str, top_n: int = 3) -> dict[str, list[str]]:
    return {}
