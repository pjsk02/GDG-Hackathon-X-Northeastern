"""Gate thresholds tuned on the VALIDATION slice (F1).

Owner: A (Je). sentinel/pipeline.py calls load() on every ticket.

Contract (keep stable):
    load(settings) -> {"triage_confidence_min": float,
                       "retrieval_similarity_min": float,
                       "high_priority_alert_probability": float}

Reads data/sentinel/thresholds.json when it exists (written by eval/tune_thresholds.py), otherwise
falls back to the values in shared/settings.py. Never tune on the holdout.
"""

from __future__ import annotations

import json
from pathlib import Path

THRESHOLDS_PATH = Path("data/sentinel/thresholds.json")
KEYS = ("triage_confidence_min", "retrieval_similarity_min", "high_priority_alert_probability")


def load(settings) -> dict[str, float]:
    values = {k: float(getattr(settings, k)) for k in KEYS}
    if THRESHOLDS_PATH.exists():
        saved = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
        values.update({k: float(saved[k]) for k in KEYS if k in saved})
    return values
