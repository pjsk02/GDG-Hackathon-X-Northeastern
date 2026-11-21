"""N3 why-this-label: sentinel.explain.explain. Offline, tiny synthetic model, a few seconds. Owner: B (Shishir)."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from sentinel import explain as ex
from sentinel.explain import explain
from sentinel.triage import HEADS, TriageModel

SIGNAL = {
    "type": {"Incident": "server crashed", "Request": "need access", "Change": "upgrade plan"},
    "queue": {"IT Support": "vpn laptop", "Billing and Payments": "invoice refund", "Product Support": "app dashboard"},
    "priority": {"high": "urgent outage", "medium": "soon please", "low": "minor question"},
}
FILLER = "the a and is our we hello thanks ticket team regards".split()


def _data(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        labels = {h: str(rng.choice(list(SIGNAL[h]))) for h in HEADS}
        words = [w for h in HEADS for w in SIGNAL[h][labels[h]].split()] + list(rng.choice(FILLER, 5))
        rng.shuffle(words)
        rows.append({"subject": f"ticket {i}", "body": " ".join(words), "language": "en" if i % 2 else "de",
                     **labels})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def model() -> TriageModel:
    return TriageModel().fit(_data(300, 1), verbose=False).calibrate(_data(160, 2), verbose=False)


def test_returns_one_list_per_head_with_words_for_the_predicted_class(model):
    out = explain(model, "Server crashed\nUrgent outage, the VPN laptop is dead")
    assert set(out) == set(HEADS)
    pred = model.predict("Server crashed", "Urgent outage, the VPN laptop is dead")
    assert pred.type.label == "Incident" and pred.priority.label == "high" and pred.queue.label == "IT Support"
    words = {h: " ".join(v).lower() for h, v in out.items()}
    assert "crashed" in words["type"] or "server" in words["type"]
    assert "urgent" in words["priority"] or "outage" in words["priority"]
    assert "vpn" in words["queue"] or "laptop" in words["queue"]


def test_top_n_is_respected_and_phrases_do_not_repeat_words(model):
    text = "Server crashed\nUrgent outage urgent outage server crashed vpn laptop invoice"
    for n in (0, 1, 2, 3, 5):
        out = explain(model, text, top_n=n)
        for phrases in out.values():
            assert len(phrases) <= n
            content = [w.lower() for p in phrases for w in p.split() if w.lower() not in ex.STOPWORDS]
            assert len(content) == len(set(content))  # no content word shown twice


def test_keeps_the_ticket_casing_and_skips_stopwords_and_numbers(model):
    out = explain(model, "VPN Laptop\nThe VPN laptop 12345 is down", top_n=5)
    flat = [p for v in out.values() for p in v]
    assert all(p.lower() not in ex.STOPWORDS for p in flat)
    assert all(not p.replace(" ", "").isdigit() for p in flat)
    assert any(p in ("VPN", "Laptop", "laptop", "VPN laptop", "VPN Laptop") for p in out["queue"])


def test_only_positive_evidence_is_returned(model):
    # Words pointing at OTHER classes must not be offered as the reason for the predicted one.
    out = explain(model, "Minor question\nminor question minor question, invoice refund", top_n=5)
    assert "urgent" not in " ".join(out["priority"]).lower()


@pytest.mark.parametrize("text", ["", "   ", "x", "!!! ??? 🚀🚀", "12345 67890", "ö", "a" * 5000, "Hilfe " * 1000])
def test_never_raises_on_odd_text(model, text):
    out = explain(model, text)
    assert set(out) == set(HEADS)
    assert all(isinstance(v, list) and all(isinstance(p, str) and p for p in v) for v in out.values())


@pytest.mark.parametrize("bad_model", [None, object(), "not a model"])
def test_unusable_model_gives_empty_dict(bad_model):
    assert explain(bad_model, "VPN down") == {}


def test_works_on_an_uncalibrated_model_and_follows_its_label():
    m = TriageModel().fit(_data(200, 3), verbose=False)
    assert not m.is_calibrated
    out = explain(m, "Need access\nneed access please")
    assert set(out) == set(HEADS)
    assert "access" in " ".join(out["type"]).lower() or "need" in " ".join(out["type"]).lower()


def test_cache_is_reused_and_rebuilt_when_a_head_is_swapped():
    m = TriageModel().fit(_data(300, 1), verbose=False)
    explain(m, "server crashed")
    first = m._explain_cache
    explain(m, "urgent outage")
    assert m._explain_cache is first  # same heads -> cached arrays reused
    # Same data and seed -> same vocabulary, so the new head fits this vectorizer (like a retrained champion).
    m.heads = {**m.heads, "priority": TriageModel().fit(_data(300, 1), verbose=False).heads["priority"]}
    explain(m, "urgent outage")
    assert m._explain_cache is not first


def test_fast_enough(model):
    explain(model, "warm up")
    t0 = time.perf_counter()
    for _ in range(50):
        explain(model, "Server crashed\nUrgent outage, the VPN laptop is dead, invoice refund please")
    assert (time.perf_counter() - t0) * 1000 / 50 < 20  # ~1 ms on the real model; generous for slow CI


def test_phrases_never_span_punctuation_but_keep_hyphenated_words():
    assert ex._as_written("Is it the service? Thank you", ("service", "thank")) is None
    assert ex._as_written("Das Projektmanagement-SaaS bricht ab", ("projektmanagement", "saas")) == "Projektmanagement-SaaS"
    assert ex._as_written("Our VPN  gateway", ("vpn", "gateway")) == "VPN  gateway"
    assert ex._as_written("nothing here", ("vpn",)) == "vpn"  # unigram not found as a word: shown lowercase


def test_feature_cache_is_reused_after_predict_and_never_stale(model):
    model.predict("Server crashed", "urgent outage")
    text = "Server crashed\nurgent outage"
    X = model._last_features[2]
    assert model.features([text]) is X  # explain() after predict() reuses the same rows
    other = model.features(["minor question\ninvoice refund"])
    assert other is not X and (other != X).nnz > 0  # a different ticket is transformed afresh
    assert explain(model, text) == explain(model, text)
    batch = model.features([text, text])
    assert batch.shape[0] == 2  # batches are never served from the single-text cache


def test_refit_in_place_clears_the_feature_cache():
    m = TriageModel().fit(_data(200, 5), verbose=False)
    m.predict("Server crashed", "urgent outage")
    stale = m._last_features[2]
    m.fit(_data(200, 6), verbose=False)  # same vectorizer object, new vocabulary
    assert m.features(["Server crashed\nurgent outage"]) is not stale
