"""Offline tests for eval/safety_dial.py (owner A). Synthetic signals, no dataset or index."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from eval import safety_dial as sd

GRID = {
    "triage_confidence_min": [0.3, 0.5, 0.7],
    "high_priority_alert_probability": [0.2, 0.5, 0.8],
    "retrieval_similarity_min": [0.0, 0.5, 0.7],
}


def _signals(n: int = 300, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    is_hpi = rng.random(n) < 0.2
    return pd.DataFrame({
        "ticket_id": [f"TKT-{i:05d}" for i in range(n)],
        "pred_type": np.where(is_hpi & (rng.random(n) < 0.6), "Incident", rng.choice(["Request", "Problem"], n)),
        "pred_priority": np.where(is_hpi & (rng.random(n) < 0.6), "high", rng.choice(["medium", "low"], n)),
        "triage_confidence": rng.uniform(0.2, 1.0, n),
        "p_high": np.clip(rng.normal(np.where(is_hpi, 0.6, 0.3), 0.15), 0, 1),
        "top_similarity": rng.uniform(0.3, 0.9, n),
        "r5": rng.random(n) < 0.03,
        "is_hpi": is_hpi,
    })


def test_json_has_exactly_the_agreed_shape(tmp_path):
    dial, _, _, source = sd.build_dial(_signals(), GRID, thresholds_path=tmp_path / "missing.json")
    assert set(dial) == {"generated_at", "split", "points", "chosen"}
    assert dial["split"] == "validation"
    assert dial["points"], "no dial points"
    keys = {"triage_confidence_min", "high_priority_alert_probability", "retrieval_similarity_min",
            "oncall_rate", "review_rate", "auto_rate", "hpi_recall"}
    for p in [*dial["points"], dial["chosen"]]:
        assert set(p) == keys
        assert all(isinstance(v, float) for v in p.values())
        assert abs(p["oncall_rate"] + p["review_rate"] + p["auto_rate"] - 1.0) < 1e-3
    assert "missing" in source
    json.dumps(dial)  # serialisable


def test_frontier_is_monotone_lenient_to_strict():
    points = sd.tt.sweep(_signals(), GRID)
    front = sd.frontier(points)
    assert front["oncall_rate"].is_monotonic_increasing
    assert front["hpi_recall"].is_monotonic_increasing
    # nothing in the sweep dominates a frontier point
    for _, f in front.iterrows():
        dominated = points[(points["oncall_rate"] <= f["oncall_rate"]) & (points["hpi_recall"] > f["hpi_recall"])]
        assert dominated.empty


def test_frontier_thinning_keeps_both_ends():
    pts = pd.DataFrame({"oncall_rate": np.linspace(0, 1, 100), "hpi_recall": np.linspace(0, 1, 100),
                        "escalation_rate": np.linspace(0, 1, 100)})
    front = sd.frontier(pts, max_points=10)
    assert len(front) == 10
    assert front["oncall_rate"].iloc[0] == 0 and front["oncall_rate"].iloc[-1] == 1


def test_chosen_comes_from_thresholds_json(tmp_path):
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps({"triage_confidence_min": 0.5, "high_priority_alert_probability": 0.5,
                                "retrieval_similarity_min": 0.5}), encoding="utf-8")
    dial, _, _, source = sd.build_dial(_signals(), GRID, thresholds_path=path)
    assert source == str(path)
    assert (dial["chosen"]["triage_confidence_min"], dial["chosen"]["high_priority_alert_probability"],
            dial["chosen"]["retrieval_similarity_min"]) == (0.5, 0.5, 0.5)


def test_png_is_written(tmp_path):
    sig = _signals()
    dial, _, _, _ = sd.build_dial(sig, GRID, thresholds_path=tmp_path / "missing.json")
    baseline = sd.tt.evaluate_point(sig, 0.55, 0.5, 0.55)
    png = sd.plot(dial, baseline, tmp_path / "dial.png")
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
