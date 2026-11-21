"""Offline tests for eval/tune_thresholds.py (owner A). Tiny synthetic data, no dataset, no index on disk."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from eval import tune_thresholds as tt
from sentinel import dataset, escalation, thresholds
from shared.settings import Settings


def _signals(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pred_type = rng.choice(["Incident", "Request", "Problem"], n)
    pred_priority = rng.choice(["high", "medium", "low"], n)
    return pd.DataFrame({
        "ticket_id": [f"TKT-{i:05d}" for i in range(n)],
        "pred_type": pred_type,
        "pred_priority": pred_priority,
        "triage_confidence": rng.uniform(0.2, 1.0, n),
        "p_high": rng.uniform(0.0, 1.0, n),
        "top_similarity": rng.uniform(0.2, 0.9, n),
        "r5": rng.random(n) < 0.05,
        "is_hpi": rng.random(n) < 0.2,
    })


@pytest.mark.parametrize("th", [(0.55, 0.50, 0.55), (0.30, 0.20, 0.0), (0.80, 0.70, 0.6)])
def test_vectorised_rules_match_the_real_gate(th):
    c, a, s = th
    sig = _signals(150, seed=1)
    fired = tt.fired_rules(sig, c, a, s)
    for i, row in sig.iterrows():
        text = "please give me a full refund" if row["r5"] else "the printer is slow"
        gate = escalation.pre_draft_gate(
            row["pred_type"], row["pred_priority"], row["triage_confidence"], row["p_high"], row["top_similarity"],
            text, triage_confidence_min=c, retrieval_similarity_min=s, high_priority_alert_probability=a,
        )
        real = {r.split()[0] for r in gate.reasons}
        mine = {rule for rule in tt.RULES if fired[rule][i]}
        assert mine == real, (i, mine, real)


def test_tiers_use_decide_tier(monkeypatch):
    tt._TIER_CACHE.clear()
    calls = []

    def fake_decide_tier(decision, reasons):
        calls.append(tuple(reasons))
        if not reasons:
            return "AUTO_DRAFT"
        return "PAGE_ONCALL" if any(r.startswith(("R1", "R2", "R5")) for r in reasons) else "AGENT_REVIEW"

    monkeypatch.setattr(escalation, "decide_tier", fake_decide_tier)
    sig = _signals()
    p = tt.evaluate_point(sig, 0.55, 0.5, 0.55)
    assert calls, "decide_tier was not called"
    assert p["oncall_rate"] + p["review_rate"] + p["auto_rate"] == pytest.approx(1.0, abs=1e-3)
    assert p["review_rate"] > 0
    tt._TIER_CACHE.clear()


def test_looser_thresholds_never_lower_recall():
    sig = _signals()
    strict = tt.evaluate_point(sig, 0.3, 0.7, 0.0)
    loose = tt.evaluate_point(sig, 0.8, 0.2, 0.6)
    assert loose["hpi_recall"] >= strict["hpi_recall"]
    assert loose["escalation_rate"] >= strict["escalation_rate"]


def test_choose_picks_lowest_oncall_meeting_target():
    pts = pd.DataFrame([
        {"hpi_recall": 0.95, "oncall_rate": 0.50, "escalation_rate": 0.6},
        {"hpi_recall": 0.91, "oncall_rate": 0.30, "escalation_rate": 0.4},
        {"hpi_recall": 0.80, "oncall_rate": 0.10, "escalation_rate": 0.2},
    ])
    best, met = tt.choose(pts, 0.90)
    assert met and best["oncall_rate"] == 0.30
    best, met = tt.choose(pts, 0.99)
    assert not met and best["hpi_recall"] == 0.95


def test_similarity_skips_the_ticket_itself():
    ids = ["TKT-00001", "TKT-00002", "TKT-00003"]
    matrix = np.eye(3, dtype=np.float32)
    matrix[2] = np.array([0.6, 0.8, 0.0], dtype=np.float32)

    class FakeEmbedder:
        name = "fake"

        def embed(self, texts, *, is_query=False):
            return np.array([matrix[int(t)] for t in texts], dtype=np.float32)

    store = SimpleNamespace(embedder=FakeEmbedder(), _matrix=lambda: (ids, matrix))
    sims = tt.top_similarity_excluding_self(store, ["0", "1"], ["TKT-00001", "TKT-00002"])
    # without the self-hit both would be 1.0; the next best is row 2
    assert sims.tolist() == pytest.approx([0.6, 0.8])


def test_similarity_fallback_uses_search_k_plus_one():
    def hit(tid, score):
        return SimpleNamespace(chunk=SimpleNamespace(id=tid, metadata={"ticket_id": tid}), score=score)

    store = SimpleNamespace(search=lambda text, k: [hit("TKT-1", 1.0), hit("TKT-9", 0.42)][:k])
    assert tt.top_similarity_excluding_self(store, ["x"], ["TKT-1"]).tolist() == pytest.approx([0.42])


def test_load_train_val_never_reads_the_holdout(tmp_path, monkeypatch):
    kb = pd.DataFrame({"ticket_id": [f"TKT-{i:05d}" for i in range(20)], "subject": "s", "body": "b",
                       "type": "Incident", "priority": "high"})
    kb_path = tmp_path / "kb_train.csv"
    kb.to_csv(kb_path, index=False)
    holdout = tmp_path / "holdout_test.csv"  # does not exist; reading or building it would fail the test
    monkeypatch.setattr(dataset, "KB_PATH", kb_path)
    monkeypatch.setattr(dataset, "TEST_PATH", holdout)
    monkeypatch.setattr(dataset, "load_split", lambda: pytest.fail("load_split reads the holdout"))
    train, val = tt.load_train_val()
    assert (len(train), len(val)) == (18, 2)
    assert val["ticket_id"].tolist() == ["TKT-00018", "TKT-00019"]
    assert not holdout.exists()


def test_written_json_is_what_thresholds_load_returns(tmp_path, monkeypatch):
    sig = _signals()
    chosen, met = tt.choose(tt.sweep(sig, tt.build_grid(sig)))
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps({**{k: chosen[k] for k in tt.KEYS}, "validation": {}}), encoding="utf-8")
    monkeypatch.setattr(thresholds, "THRESHOLDS_PATH", path)
    loaded = thresholds.load(Settings())
    assert loaded == {k: pytest.approx(float(chosen[k])) for k in tt.KEYS}
