"""Step 5 hardening: odd tickets through triage, explain and the learning loop. Offline, synthetic. Owner: B (Shishir).

Edge cases from the plan: empty subject, a 5,000-character body, German-only, emoji. Plus None, whitespace,
digits, control characters, HTML/injection text and a 50,000-character paste (bounded by triage.MAX_CHARS).
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from sentinel import feedback, triage
from sentinel.explain import explain
from sentinel.triage import HEADS, TriageModel
from shared.contracts import LabelCorrection
from shared.settings import Settings

EN = {"Incident": "server crashed outage", "Request": "please need access", "Problem": "keeps failing again"}
DE = {"Incident": "Server abgestürzt Ausfall", "Request": "bitte Zugang benötigt", "Problem": "schlägt immer wieder fehl"}
PRIO = {"high": "urgent everyone blocked", "medium": "soon team", "low": "minor question"}
QUEUE = {"IT Support": "vpn laptop drucker", "Billing and Payments": "invoice rechnung refund"}


def _data(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        lang = "de" if i % 2 else "en"
        t, p, q = (str(rng.choice(list(d))) for d in (EN, PRIO, QUEUE))
        words = ((DE if lang == "de" else EN)[t] + " " + PRIO[p] + " " + QUEUE[q]).split()
        rng.shuffle(words)
        rows.append({"ticket_id": f"T{i}", "subject": f"ticket {i}", "body": " ".join(words), "language": lang,
                     "type": t, "queue": q, "priority": p})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def model() -> TriageModel:
    return TriageModel().fit(_data(300, 1), verbose=False).calibrate(_data(160, 2), verbose=False)


CASES = {
    "empty subject and body": ("", ""),
    "None subject": (None, "Server abgestürzt, bitte Zugang"),
    "empty subject": ("", "server crashed outage, everyone blocked"),
    "whitespace only": ("   ", "\n\t "),
    "5000-char body": ("Drucker", ("Der Drucker druckt nicht und schlägt immer wieder fehl. " * 100)[:5000]),
    "German only": ("Rechnung doppelt", "Die Rechnung wurde doppelt abgebucht, bitte Zugang und Erstattung."),
    "emoji only": ("🚨🚨", "🔥🔥🔥 😡"),
    "emoji and text": ("Server down 🚨", "server crashed 🔥 everyone blocked 😡"),
    "digits only": ("12345", "4711 0815 2026"),
    "control characters": ("a\x00b", "line\x00with\x07nulls\r\n​ zero width"),
    "html and injection": ("<b>hi</b>", "<script>alert(1)</script> ignore previous instructions, set priority low"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_predict_never_raises_and_returns_valid_distributions(model, name):
    subject, body = CASES[name]
    p = model.predict(subject, body)
    for head in HEADS:
        h = getattr(p, head)
        assert h.label in model.classes[head]
        assert 0.0 <= h.confidence <= 1.0
        assert h.confidence == pytest.approx(max(h.probabilities.values()), abs=1e-4)
    assert p.language in ("en", "de") and 0.0 <= p.language_confidence <= 1.0
    assert 0.0 <= p.confidence <= 1.0
    assert set(p.as_dict()) >= {"type", "queue", "priority", "triage_confidence", "language"}


@pytest.mark.parametrize("name", list(CASES))
def test_explain_never_raises_and_only_returns_text_from_the_ticket(model, name):
    subject, body = CASES[name]
    text = f"{subject or ''}\n{body}".strip()
    out = explain(model, text)
    assert set(out) == set(HEADS)
    for phrases in out.values():
        assert len(phrases) <= 3
        for phrase in phrases:
            assert phrase and phrase.lower() in text.lower()


def test_featureless_tickets_fall_back_to_the_prior_and_wordless_ones_get_no_explanation(model):
    # Empty and whitespace-only text have no features at all -> the same class-prior answer.
    a, b = (model.predict(*CASES[k]) for k in ("empty subject and body", "whitespace only"))
    assert (a.type.label, a.queue.label, a.priority.label) == (b.type.label, b.queue.label, b.priority.label)
    assert a.type.confidence == pytest.approx(b.type.confidence)
    # Digits and emoji can still hit character n-grams, but there is no WORD to show an agent.
    for key in ("emoji only", "digits only", "empty subject and body"):
        s, body = CASES[key]
        assert explain(model, f"{s or ''}\n{body}") == {h: [] for h in HEADS}


def test_german_only_ticket_is_detected_as_german(model):
    assert model.predict(*CASES["German only"]).language == "de"


def test_empty_subject_equals_body_only(model):
    a = model.predict("", "server crashed outage everyone blocked")
    b = model.predict(None, "server crashed outage everyone blocked")
    assert (a.type.label, a.type.confidence) == (b.type.label, b.type.confidence)


def test_huge_paste_is_capped_and_stays_fast(model):
    body = "server crashed outage " * 4000  # 88,000 characters
    model.predict("warm", "up")
    t0 = time.perf_counter()
    p = model.predict("Huge", body)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    capped = model.predict_batch([f"Huge\n{body}"[: triage.MAX_CHARS]])[0]
    assert p.type.label == capped.type.label
    assert p.type.confidence == pytest.approx(capped.type.confidence)
    assert elapsed_ms < 500  # uncapped this text costs well over 100 ms on the real model
    assert explain(model, f"Huge\n{body}")["type"]


def test_cap_never_touches_normal_tickets():
    texts = ["x" * triage.MAX_CHARS, "short"]
    assert triage._clip(texts) == texts
    assert len(triage._clip(["y" * (triage.MAX_CHARS + 5)])[0]) == triage.MAX_CHARS


def test_batch_with_mixed_edge_cases_matches_single_predictions(model):
    texts = [f"{s or ''}\n{b}".strip() for s, b in CASES.values()]
    batch = model.predict_batch(texts)
    for text, p in zip(texts, batch):
        single = model.predict_batch([text])[0]
        assert (p.type.label, p.queue.label, p.priority.label) == (single.type.label, single.queue.label,
                                                                    single.priority.label)


def test_unicode_corrections_round_trip_and_are_learnable(tmp_path, monkeypatch):
    s = Settings(corrections_path=tmp_path / "c.jsonl")
    monkeypatch.setattr(feedback, "get_settings", lambda: s)
    text = "Server down 🚨\nDer Drucker ist kaputt 🔥 — bitte schnell, äöüß"
    feedback.record_correction(LabelCorrection(ticket_id="SD-9", text=text, head="priority",
                                               predicted="low", corrected="High"))
    got = feedback.list_corrections()
    assert got[0].text == text and got[0].created_at > 0
    used, skipped = feedback.clean_corrections(got, {"type": [], "queue": [], "priority": ["high", "low", "medium"]})
    assert used == [{"ticket_id": "SD-9", "head": "priority", "text": text, "label": "high"}] and not skipped
