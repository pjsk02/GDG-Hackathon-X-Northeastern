"""Learning loop: agent label corrections + champion/challenger retraining (N8).

Owner: B (Shishir). PARTIAL STUB: record/list work now (JSON lines), retraining is not built yet.
The manager page (owner E) calls these functions; keep the signatures stable.

Contract:
    record_correction(c: LabelCorrection) -> None
    list_corrections() -> list[LabelCorrection]
    retrain_challenger() -> dict
        -> {"status": "promoted" | "kept_champion" | "not_implemented" | "error",
            "champion": {"type_macro_f1": ..., "priority_macro_f1": ..., "hpi_recall": ...},
            "challenger": {...}, "corrections_used": int, "message": str}

Retrain on the train slice + corrections, score both models on the VALIDATION slice
(sentinel.dataset.load_train_val_test), promote only if Macro-F1 and high-priority incident recall
do not drop. Never read the holdout here.
"""

from __future__ import annotations

import json
import time

from shared.contracts import LabelCorrection
from shared.settings import get_settings


def record_correction(c: LabelCorrection) -> None:
    path = get_settings().corrections_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not c.created_at:
        c.created_at = time.time()
    with path.open("a", encoding="utf-8") as f:
        f.write(c.model_dump_json() + "\n")


def list_corrections() -> list[LabelCorrection]:
    path = get_settings().corrections_path
    if not path.exists():
        return []
    return [LabelCorrection.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def retrain_challenger() -> dict:
    return {
        "status": "not_implemented",
        "corrections_used": len(list_corrections()),
        "message": "Retraining is not built yet (owner B, sentinel/feedback.py).",
    }
