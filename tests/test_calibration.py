"""F2 calibration: sentinel.calibration (ECE, reliability, report, plot) and TriageModel.calibrate.

Offline, tiny synthetic data, a few seconds. Owner: B (Shishir).
"""

from __future__ import annotations

import time

import joblib
import numpy as np
import pandas as pd
import pytest

from sentinel import calibration
from sentinel.triage import CALIBRATION_METHODS, HEADS, TriageModel

WORDS = {
    "type": {"Incident": "outage down crashed", "Request": "please provide access", "Problem": "keeps failing again"},
    "queue": {"IT Support": "vpn laptop printer", "Billing and Payments": "invoice refund charge",
              "Product Support": "app feature dashboard"},
    "priority": {"high": "urgent critical everyone", "medium": "soon important team", "low": "whenever minor question"},
}
NOISE = "hello thanks regards ticket issue help support customer team update system account".split()


def _synthetic(n: int, seed: int, label_noise: float = 0.25) -> pd.DataFrame:
    """Tickets whose words point at their labels, with label noise so the model is not trivially sure."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        labels = {h: rng.choice(list(WORDS[h])) for h in HEADS}
        words = [w for h in HEADS for w in WORDS[h][labels[h]].split() if rng.random() < 0.7]
        words += list(rng.choice(NOISE, size=4))
        rng.shuffle(words)
        for h in HEADS:  # flip some labels: the text no longer settles the answer
            if rng.random() < label_noise:
                labels[h] = rng.choice(list(WORDS[h]))
        lang = "de" if i % 3 == 0 else "en"
        body = " ".join(words) + (" bitte danke" if lang == "de" else " please thanks")
        rows.append({"subject": f"ticket {i}", "body": body, "language": lang, **labels})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _synthetic(400, seed=1), _synthetic(240, seed=2), _synthetic(200, seed=3)


@pytest.fixture(scope="module")
def model(data) -> TriageModel:
    train, val, _ = data
    return TriageModel().fit(train, verbose=False).calibrate(val, verbose=False)


# -- reliability / ECE ------------------------------------------------------------------------


def test_ece_is_zero_when_confidence_matches_accuracy():
    # 10 tickets at confidence 0.8, 8 of them right -> perfectly calibrated bin.
    classes = np.array(["a", "b"])
    proba = np.tile([0.8, 0.2], (10, 1))
    y = np.array(["a"] * 8 + ["b"] * 2)
    r = calibration.reliability(proba, classes, y)
    assert r["ece"] == pytest.approx(0.0, abs=1e-9)
    assert r["accuracy"] == pytest.approx(0.8)
    assert len(r["bins"]) == calibration.N_BINS
    assert sum(b["count"] for b in r["bins"]) == 10


def test_ece_measures_overconfidence_and_puts_certainty_in_last_bin():
    classes = np.array(["a", "b"])
    proba = np.tile([1.0, 0.0], (4, 1))
    y = np.array(["a", "b", "b", "b"])  # 100% sure, 25% right
    r = calibration.reliability(proba, classes, y)
    assert r["ece"] == pytest.approx(0.75)
    assert r["bins"][-1]["count"] == 4  # confidence 1.0 is in bin 0.9-1.0, not an 11th bin


def test_reliability_handles_empty_and_unseen_labels():
    assert calibration.reliability(np.zeros((0, 2)), np.array(["a", "b"]), np.array([]))["ece"] == 0.0
    r = calibration.reliability(np.array([[0.6, 0.4], [0.3, 0.7]]), np.array(["a", "b"]), np.array(["a", "zzz"]))
    assert np.isfinite(r["log_loss"])  # the unseen label is dropped from log-loss instead of raising


# -- TriageModel.calibrate --------------------------------------------------------------------


def test_calibrate_picks_a_method_per_head_on_validation(model):
    assert model.is_calibrated
    assert model.calibrated_on == 240
    for head in HEADS:
        method = model.calibration_method[head]
        assert method in ("none", *CALIBRATION_METHODS)
        stats = model.calibration_selection[head]
        assert "none" in stats and "temperature" in stats
        # The winner has the lowest out-of-fold log-loss among candidates that keep Macro-F1.
        floor = stats["none"]["macro_f1"] - 0.005
        eligible = {m: v["log_loss"] for m, v in stats.items() if v["macro_f1"] >= floor}
        assert stats[method]["log_loss"] == min(eligible.values())


def test_calibrated_probabilities_are_distributions(model, data):
    texts = ["urgent outage vpn everyone", "invoice refund whenever", ""]
    for head, (proba, classes) in model.predict_proba_heads(texts).items():
        assert proba.shape == (3, len(classes))
        assert np.allclose(proba.sum(axis=1), 1.0)
        assert (proba >= 0).all()


def test_temperature_scaling_never_changes_the_predicted_label(data):
    train, val, test = data
    m = TriageModel().fit(train, verbose=False).calibrate(val, methods=("temperature",), verbose=False)
    texts = [f"{r['subject']}\n{r['body']}" for r in test.to_dict("records")]
    raw = m.predict_proba_heads(texts, calibrated=False)
    cal = m.predict_proba_heads(texts, calibrated=True)
    for head in HEADS:
        assert (raw[head][0].argmax(1) == cal[head][0].argmax(1)).all()
        if m.calibration_method[head] == "temperature":
            assert 0.05 <= m.calibrators[head] <= 20.0


def test_calibration_fixes_an_overconfident_model_on_fresh_data():
    """Heavy label noise + a small train set makes the raw heads overconfident; calibration must help.

    Asserted on log-loss (a proper scoring rule). ECE over a few hundred tickets in 10 bins moves by
    +-0.03 from noise alone, so it only gets a tolerance.
    """
    train, val, test = _synthetic(300, 10, 0.4), _synthetic(600, 20, 0.4), _synthetic(600, 30, 0.4)
    m = TriageModel().fit(train, verbose=False).calibrate(val, verbose=False)
    rep = calibration.report(m, test)
    for head in HEADS:
        h = rep["heads"][head]
        assert h["uncalibrated"]["mean_confidence"] > h["uncalibrated"]["accuracy"]  # really overconfident
        assert h["calibrated"]["log_loss"] < h["uncalibrated"]["log_loss"]
        assert h["calibrated"]["ece"] <= h["uncalibrated"]["ece"] + 0.03


def test_predict_stays_fast_and_uses_calibrated_confidence(model):
    model.predict("warmup", "warmup")
    t0 = time.perf_counter()
    for _ in range(20):
        p = model.predict("VPN down", "urgent outage vpn everyone")
    per_ticket_ms = (time.perf_counter() - t0) * 1000 / 20
    assert per_ticket_ms < 50  # real model is ~1 ms; generous for slow CI machines
    proba, classes = model.predict_proba_heads(["VPN down\nurgent outage vpn everyone"])["type"]
    assert p.type.confidence == pytest.approx(float(proba[0].max()), abs=1e-9)
    assert 0.0 <= p.confidence <= 1.0


# -- persistence -------------------------------------------------------------------------------


def test_save_load_round_trip_keeps_calibration_and_metadata(model, tmp_path):
    path = model.save(tmp_path / "m.joblib")
    parts = joblib.load(path)
    assert parts["calibrated"] is True
    assert parts["trained_on"] == 400
    assert set(parts["classes"]) == set(HEADS)
    loaded = TriageModel.load(path)
    assert loaded.calibration_method == model.calibration_method
    texts = ["urgent outage vpn everyone"]
    for head in HEADS:
        assert np.allclose(loaded.predict_proba_heads(texts)[head][0], model.predict_proba_heads(texts)[head][0])
    meta = loaded.metadata()
    assert meta["calibrated"] and meta["trained_on"] == 400


def test_model_saved_before_calibration_loads_as_uncalibrated(model, tmp_path):
    path = tmp_path / "old.joblib"
    joblib.dump({"vectorizer": model.vectorizer, "heads": model.heads, "lang_vectorizer": model.lang_vectorizer,
                 "lang_head": model.lang_head, "trained_on": 400}, path)
    old = TriageModel.load(path)
    assert not old.is_calibrated
    assert old.predict("x", "urgent outage").type.label in WORDS["type"]


# -- report / plot / write ---------------------------------------------------------------------


def test_report_shape(model, data):
    rep = calibration.report(model, data[2])
    assert rep["tickets"] == 200
    assert rep["model"]["calibrated"] is True
    assert set(rep["heads"]) == set(HEADS)
    for h in rep["heads"].values():
        for key in ("uncalibrated", "calibrated"):
            assert set(h[key]) == {"ece", "log_loss", "accuracy", "mean_confidence", "bins"}
            assert len(h[key]["bins"]) == calibration.N_BINS


def test_report_on_uncalibrated_model_has_no_after(data):
    m = TriageModel().fit(data[0], verbose=False)
    rep = calibration.report(m, data[2])
    assert all(h["calibrated"] is None for h in rep["heads"].values())


def test_write_creates_json_and_png(model, data, tmp_path):
    out, png = tmp_path / "eval" / "calibration.json", tmp_path / "eval" / "calibration.png"
    rep = calibration.write(model, data[2], split="synthetic", out=out, png=png)
    assert rep["split"] == "synthetic"
    assert out.exists() and png.exists() and png.stat().st_size > 1000
