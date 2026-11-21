"""N8 learning loop: sentinel.feedback. Offline, tiny synthetic kb and model in tmp_path. Owner: B (Shishir)."""

from __future__ import annotations

import time

import joblib
import numpy as np
import pandas as pd
import pytest

from sentinel import dataset, feedback, triage
from sentinel.triage import HEADS, TriageModel
from shared.contracts import LabelCorrection
from shared.settings import Settings

SIGNAL = {
    "type": {"Incident": "server crashed", "Request": "need access", "Change": "upgrade plan"},
    "queue": {"IT Support": "vpn laptop", "Billing and Payments": "invoice refund", "Product Support": "app dashboard"},
    "priority": {"high": "urgent outage", "medium": "soon please", "low": "minor question"},
}
FILLER = "the a and is our we hello thanks ticket team regards".split()


def _kb(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        labels = {h: str(rng.choice(list(SIGNAL[h]))) for h in HEADS}
        words = [w for h in HEADS for w in SIGNAL[h][labels[h]].split()] + list(rng.choice(FILLER, 5))
        rng.shuffle(words)
        rows.append({"ticket_id": f"TKT-{i:05d}", "subject": f"ticket {i}", "body": " ".join(words),
                     "language": "en" if i % 2 else "de", "answer": "", **labels})
    return pd.DataFrame(rows)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A champion trained on the synthetic train slice, saved in tmp; the real model is never touched."""
    kb = _kb()
    kb_path = tmp_path / "kb_train.csv"
    kb.to_csv(kb_path, index=False)
    train, val = dataset.split_train_val(kb)
    model_path = tmp_path / "triage_model.joblib"
    TriageModel().fit(train, verbose=False).calibrate(val, verbose=False).save(model_path)
    monkeypatch.setattr(triage, "MODEL_PATH", model_path)
    monkeypatch.setattr(triage, "_CACHED", None)
    return {"kb": kb, "kb_path": kb_path, "model_path": model_path, "train": train, "val": val}


def _c(text: str, head: str, predicted: str, corrected: str, tid: str = "SD-1", at: float = 0.0) -> LabelCorrection:
    return LabelCorrection(ticket_id=tid, text=text, head=head, predicted=predicted, corrected=corrected,
                           created_at=at)


def _run(env, corrections, **kw):
    return feedback.run_retrain(corrections, model_path=env["model_path"], kb_path=env["kb_path"], **kw)


# -- cleaning ---------------------------------------------------------------------------------


def test_clean_normalises_labels_and_skips_bad_corrections():
    classes = {"type": ["Change", "Incident", "Request"], "queue": ["IT Support"], "priority": ["high", "low", "medium"]}
    used, skipped = feedback.clean_corrections([
        _c("vpn down", "priority", "low", " High ", tid="A"),        # case/space -> "high"
        _c("vpn down", "type", "Request", "Outage", tid="A"),        # unknown label
        _c("billing", "priority", "low", "low", tid="B"),            # no change
        _c("   ", "type", "Request", "Incident", tid="C"),            # empty text
    ], classes)
    assert used == [{"ticket_id": "A", "head": "priority", "text": "vpn down", "label": "high"}]
    reasons = sorted(r for _, r in skipped)
    assert reasons == ["empty text", "no change (corrected == predicted)", "unknown type label 'Outage'"]


def test_latest_correction_wins_even_when_recorded_out_of_order():
    classes = {"type": ["Change", "Incident", "Request"], "queue": [], "priority": []}
    used, skipped = feedback.clean_corrections([
        _c("printer jam", "type", "Request", "Change", tid="X", at=200.0),
        _c("printer jam", "type", "Request", "Incident", tid="X", at=100.0),  # older, arrives later
    ], classes)
    assert [u["label"] for u in used] == ["Change"]
    assert [r for _, r in skipped] == ["superseded by a later correction"]


# -- fast paths and safety --------------------------------------------------------------------


def test_no_corrections_keeps_champion_without_training(env, monkeypatch):
    monkeypatch.setattr(feedback, "build_challenger", lambda *a, **k: pytest.fail("must not train"))
    before = env["model_path"].stat().st_mtime_ns
    out = _run(env, [])
    assert out["status"] == "kept_champion" and out["corrections_used"] == 0
    assert env["model_path"].stat().st_mtime_ns == before


def test_validation_ticket_copies_are_not_trained_on(env, monkeypatch):
    monkeypatch.setattr(feedback, "build_challenger", lambda *a, **k: pytest.fail("must not train"))
    row = env["val"].iloc[0].to_dict()
    out = _run(env, [_c(dataset.ticket_text(row), "type", row["type"], next(t for t in SIGNAL["type"] if t != row["type"]))])
    assert out["status"] == "kept_champion"
    assert out["skipped_reasons"] == {"copy of a validation ticket": 1}


def test_missing_model_is_an_error_not_an_exception(tmp_path):
    out = feedback.run_retrain([_c("x y", "type", "Request", "Incident")], model_path=tmp_path / "none.joblib")
    assert out["status"] == "error" and "make sentinel-train" in out["message"]


def test_broken_input_is_reported_as_error(env):
    out = feedback.run_retrain([_c("server crashed", "type", "Request", "Incident")],
                               model_path=env["model_path"], kb_path=env["kb_path"].with_name("missing.csv"))
    assert out["status"] == "error" and "Retrain failed" in out["message"]


def test_only_one_retrain_at_a_time(env):
    assert feedback._LOCK.acquire(blocking=False)
    try:
        out = _run(env, [_c("server crashed now", "type", "Request", "Incident")])
    finally:
        feedback._LOCK.release()
    assert out["status"] == "error" and "already running" in out["message"]


def test_never_reads_the_holdout(env, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("holdout must not be read")

    monkeypatch.setattr(dataset, "load_split", boom)
    monkeypatch.setattr(dataset, "load_train_val_test", boom)
    real_read = pd.read_csv
    holdout_name = dataset.TEST_PATH.name  # tmp_path itself contains this test's name, so match the file
    monkeypatch.setattr(pd, "read_csv", lambda p, *a, **k: boom() if str(p).endswith(holdout_name) else real_read(p, *a, **k))
    out = _run(env, [_c("printer paper jammed upgrade", "type", "Request", "Change")])
    assert out["status"] in ("promoted", "kept_champion")


# -- the real loop ----------------------------------------------------------------------------


def test_real_run_returns_a_decision_with_numbers(env):
    t0 = time.perf_counter()
    out = _run(env, [_c("printer paper jammed upgrade", "type", "Request", "Change", tid="N1"),
                     _c("printer paper jammed upgrade", "priority", "low", "high", tid="N1")])
    assert out["status"] in ("promoted", "kept_champion"), out["message"]
    for side in ("champion", "challenger"):
        assert set(feedback.METRIC_KEYS) <= set(out[side])
        assert out[side]["validation_tickets"] == len(env["val"])
    assert out["corrections_used"] == 2 and out["heads_retrained"] == ["type", "priority"]
    assert out["message"] and out["duration_s"] >= 0
    assert time.perf_counter() - t0 < 60


def test_corrections_move_the_challenger_towards_the_corrected_label(env):
    champion = TriageModel.load(env["model_path"])
    text = "server crashed again"  # reads as Incident; the agents say it is a Change
    assert champion.predict(None, text).type.label == "Incident"
    used = [{"ticket_id": f"N{i}", "head": "type", "text": text, "label": "Change"} for i in range(3)]
    challenger, heads = feedback.build_challenger(champion, env["train"], used, weight=5.0)
    assert heads == ["type"]
    p_old = champion.predict_proba_heads([text], calibrated=False)["type"]
    p_new = challenger.predict_proba_heads([text], calibrated=False)["type"]
    j = list(p_old[1]).index("Change")
    assert p_new[0][0, j] > p_old[0][0, j]
    assert challenger.heads["queue"] is champion.heads["queue"]  # untouched heads are shared, not refit
    assert challenger.vectorizer is champion.vectorizer


def _fake_scores(monkeypatch, champion: dict, challenger: dict):
    calls = iter([champion, challenger])
    monkeypatch.setattr(feedback, "score", lambda model, val: dict(next(calls), validation_tickets=len(val)))


BASE = {"type_macro_f1": 0.80, "queue_macro_f1": 0.50, "priority_macro_f1": 0.60, "hpi_recall": 0.70}


def test_promotes_when_no_metric_drops_and_keeps_a_backup(env, monkeypatch):
    _fake_scores(monkeypatch, BASE, dict(BASE, priority_macro_f1=0.61))
    live = TriageModel.load(env["model_path"])
    monkeypatch.setattr(triage, "_CACHED", live)
    old_bytes = env["model_path"].read_bytes()

    out = _run(env, [_c("printer paper jammed", "priority", "low", "high")])

    assert out["status"] == "promoted", out["message"]
    backup = env["model_path"].with_name(out["backup_path"].split("\\")[-1].split("/")[-1])
    assert backup.exists() and backup.read_bytes() == old_bytes
    saved = joblib.load(env["model_path"])
    assert saved["corrections_used"] == 1 and saved["calibrated"] is True
    assert triage._CACHED is None  # next get_model() reloads from disk
    assert live.corrections_used == 1  # the object the pipeline already holds was updated in place
    assert live.predict("x", "urgent outage").priority.label in SIGNAL["priority"]


@pytest.mark.parametrize("worse, drop", [("type_macro_f1", 0.001), ("priority_macro_f1", 0.001),
                                         ("hpi_recall", 0.001), ("queue_macro_f1", 0.0051)])
def test_keeps_champion_if_a_gated_metric_drops(env, monkeypatch, worse, drop):
    _fake_scores(monkeypatch, BASE, {**{k: v + 0.05 for k, v in BASE.items()}, worse: BASE[worse] - drop})
    before = env["model_path"].read_bytes()
    out = _run(env, [_c("printer paper jammed", "priority", "low", "high")])
    assert out["status"] == "kept_champion"
    assert worse in out["message"]
    assert env["model_path"].read_bytes() == before
    assert not list(env["model_path"].parent.glob("*.backup-*"))


def test_unchanged_second_click_is_instant_and_cached(env, monkeypatch):
    corr = [_c("printer paper jammed", "priority", "low", "high")]
    first = _run(env, corr)
    assert first["status"] in ("promoted", "kept_champion")
    monkeypatch.setattr(feedback, "build_challenger", lambda *a, **k: pytest.fail("must not retrain"))
    second = _run(env, corr)
    assert second["cached"] is True and second["status"] == "kept_champion"  # nothing new happened
    assert second["last_result"]["status"] == first["status"]
    assert second["message"].startswith("No new corrections")
    assert second["champion"] == (first["challenger"] if first["status"] == "promoted" else first["champion"])


def test_old_backups_are_pruned(env):
    champion = TriageModel.load(env["model_path"])
    for _ in range(feedback.BACKUPS_KEPT + 2):
        feedback.promote(champion, env["model_path"])
    assert len(list(env["model_path"].parent.glob("triage_model.backup-*.joblib"))) == feedback.BACKUPS_KEPT


def test_public_retrain_challenger_uses_settings_and_model_path(env, monkeypatch, tmp_path):
    s = Settings(corrections_path=tmp_path / "corrections.jsonl")
    monkeypatch.setattr(feedback, "get_settings", lambda: s)
    monkeypatch.setattr(dataset, "KB_PATH", env["kb_path"])
    feedback.record_correction(_c("printer paper jammed", "type", "Request", "Change"))
    (tmp_path / "corrections.jsonl").open("a", encoding="utf-8").write("not json\n")  # a bad line is skipped
    assert len(feedback.list_corrections()) == 1
    out = feedback.retrain_challenger()
    assert out["status"] in ("promoted", "kept_champion") and out["corrections_used"] == 1


def test_small_queue_dip_within_tolerance_still_promotes(env, monkeypatch):
    _fake_scores(monkeypatch, BASE, dict(BASE, queue_macro_f1=BASE["queue_macro_f1"] - 0.0015))
    out = _run(env, [_c("printer paper jammed", "queue", "Product Support", "IT Support")])
    assert out["status"] == "promoted", out["message"]
