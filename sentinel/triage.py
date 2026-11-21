"""Multi-task triage: type / queue / priority (+ language) with calibrated confidence.

Deliberately *not* an LLM. A linear model over TF-IDF features trains in seconds, predicts in
~1 ms, and gives a real probability from `predict_proba` — which is what the escalation gate needs.
An LLM asked for the same three labels is ~1.7 s per ticket, cannot be scored over 5.7k holdout
tickets in a hackathon, and reports confidence it has not earned. The LLM's job here is the
grounded reply, not the labels.

Word (1-2) and character (3-5) n-grams are combined: German compounds ("Zahlungsrückerstattung")
share character n-grams with their parts, so one feature space covers both languages.

    python -m sentinel.triage --train      # fit on kb_train, score on the 20% holdout
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, recall_score
from sklearn.pipeline import FeatureUnion

from sentinel import dataset

MODEL_PATH = Path("data/sentinel/triage_model.joblib")
HEADS = ("type", "queue", "priority")


@dataclass
class HeadPrediction:
    label: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass
class TriagePrediction:
    type: HeadPrediction
    queue: HeadPrediction
    priority: HeadPrediction
    language: str
    language_confidence: float
    latency_ms: float = 0.0

    @property
    def confidence(self) -> float:
        """One number for the gate: the weakest of the three heads (conservative on purpose)."""
        return min(self.type.confidence, self.queue.confidence, self.priority.confidence)

    def as_dict(self) -> dict[str, object]:
        return {
            "type": self.type.label,
            "queue": self.queue.label,
            "priority": self.priority.label,
            "type_confidence": round(self.type.confidence, 4),
            "queue_confidence": round(self.queue.confidence, 4),
            "priority_confidence": round(self.priority.confidence, 4),
            "triage_confidence": round(self.confidence, 4),
            "language": self.language,
            "language_confidence": round(self.language_confidence, 4),
            "latency_ms": round(self.latency_ms, 2),
        }


def _vectorizer() -> FeatureUnion:
    return FeatureUnion(
        [
            ("word", TfidfVectorizer(ngram_range=(1, 2), max_features=60_000, min_df=2, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=60_000, min_df=3,
                                     sublinear_tf=True)),
        ]
    )


def _classifier() -> LogisticRegression:
    # class_weight="balanced" matters: "General Inquiry" is 1.4% of the data but still has to be routable.
    return LogisticRegression(max_iter=1500, C=4.0, class_weight="balanced", n_jobs=-1)


class TriageModel:
    """One shared feature space, one linear head per target, plus a character-level language head."""

    def __init__(self) -> None:
        self.vectorizer = _vectorizer()
        self.heads: dict[str, LogisticRegression] = {}
        self.lang_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3), max_features=20_000)
        self.lang_head: LogisticRegression | None = None
        self.trained_on = 0

    # -- training ---------------------------------------------------------

    def fit(self, kb_train_df: pd.DataFrame, verbose: bool = True) -> "TriageModel":
        texts = [dataset.ticket_text(r) for r in kb_train_df.to_dict("records")]
        t0 = time.perf_counter()
        X = self.vectorizer.fit_transform(texts)
        if verbose:
            print(f"  features: {X.shape[1]:,} ({time.perf_counter() - t0:.1f}s)", flush=True)
        for head in HEADS:
            t = time.perf_counter()
            clf = _classifier()
            clf.fit(X, kb_train_df[head].astype(str))
            self.heads[head] = clf
            if verbose:
                print(f"  {head:<9} {len(clf.classes_)} classes  ({time.perf_counter() - t:.1f}s)", flush=True)
        t = time.perf_counter()
        Xl = self.lang_vectorizer.fit_transform(texts)
        self.lang_head = LogisticRegression(max_iter=1000, n_jobs=-1).fit(Xl, kb_train_df["language"].astype(str))
        if verbose:
            print(f"  language  {len(self.lang_head.classes_)} classes  ({time.perf_counter() - t:.1f}s)", flush=True)
        self.trained_on = len(kb_train_df)
        return self

    # -- inference --------------------------------------------------------

    def predict_batch(self, texts: list[str]) -> list[TriagePrediction]:
        t0 = time.perf_counter()
        X = self.vectorizer.transform(texts)
        Xl = self.lang_vectorizer.transform(texts)
        per_head: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for head in HEADS:
            clf = self.heads[head]
            per_head[head] = (clf.predict_proba(X), clf.classes_)
        lang_proba = self.lang_head.predict_proba(Xl)
        lang_classes = self.lang_head.classes_
        latency = (time.perf_counter() - t0) * 1000 / max(len(texts), 1)

        out: list[TriagePrediction] = []
        for i in range(len(texts)):
            heads = {}
            for head in HEADS:
                proba, classes = per_head[head]
                row = proba[i]
                j = int(np.argmax(row))
                top = np.argsort(-row)[:3]
                heads[head] = HeadPrediction(
                    label=str(classes[j]),
                    confidence=float(row[j]),
                    probabilities={str(classes[t]): round(float(row[t]), 4) for t in top},
                )
            li = int(np.argmax(lang_proba[i]))
            out.append(
                TriagePrediction(
                    type=heads["type"],
                    queue=heads["queue"],
                    priority=heads["priority"],
                    language=str(lang_classes[li]),
                    language_confidence=float(lang_proba[i][li]),
                    latency_ms=latency,
                )
            )
        return out

    def predict(self, subject: str | None, body: str) -> TriagePrediction:
        text = dataset.ticket_text({"subject": subject or "", "body": body or ""})
        return self.predict_batch([text])[0]

    # -- persistence ------------------------------------------------------

    def save(self, path: Path | str = MODEL_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)
        return path

    @staticmethod
    def load(path: Path | str = MODEL_PATH) -> "TriageModel":
        return joblib.load(path)


_CACHED: TriageModel | None = None


def get_model(path: Path | str = MODEL_PATH) -> TriageModel:
    """Process-wide singleton, so the UI and API load the model once."""
    global _CACHED
    if _CACHED is None:
        _CACHED = TriageModel.load(path)
    return _CACHED


# -- evaluation -----------------------------------------------------------


def evaluate(model: TriageModel, test_df: pd.DataFrame, verbose: bool = True) -> dict[str, object]:
    """Score the holdout split. Labels are read HERE ONLY, after prediction, never at inference."""
    texts = [dataset.ticket_text(r) for r in test_df.to_dict("records")]
    t0 = time.perf_counter()
    preds = model.predict_batch(texts)
    total_ms = (time.perf_counter() - t0) * 1000

    metrics: dict[str, object] = {
        "holdout_tickets": len(test_df),
        "latency_ms_per_ticket": round(total_ms / max(len(texts), 1), 3),
    }
    for head in HEADS:
        y_true = test_df[head].astype(str).tolist()
        y_pred = [getattr(p, head).label for p in preds]
        metrics[f"{head}_macro_f1"] = round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4)
        metrics[f"{head}_accuracy"] = round(float(np.mean([a == b for a, b in zip(y_true, y_pred)])), 4)
        if verbose:
            print(f"\n=== {head} ===")
            print(classification_report(y_true, y_pred, zero_division=0, digits=3))

    # Language detection (the demo detects it from raw text; the column is only the answer key).
    y_true = test_df["language"].astype(str).tolist()
    y_pred = [p.language for p in preds]
    metrics["language_accuracy"] = round(float(np.mean([a == b for a, b in zip(y_true, y_pred)])), 4)

    # The headline safety metric: of the tickets that really were high-priority Incidents,
    # how many did we catch? A miss here is an outage sitting in a queue.
    is_hpi = [(t == "Incident" and p == "high") for t, p in zip(test_df["type"], test_df["priority"])]
    pred_hpi = [(p.type.label == "Incident" and p.priority.label == "high") for p in preds]
    metrics["high_priority_incident_count"] = int(sum(is_hpi))
    metrics["high_priority_incident_recall"] = round(
        recall_score(is_hpi, pred_hpi, zero_division=0), 4
    )
    # The gate escalates on high priority alone too, so this is what actually reaches a human.
    caught_by_gate = [pred for true, pred in zip(is_hpi, [p.priority.label == "high" for p in preds]) if true]
    metrics["high_priority_incident_recall_via_gate"] = round(
        float(np.mean(caught_by_gate)) if caught_by_gate else 0.0, 4
    )
    metrics["high_priority_recall"] = round(
        recall_score([p == "high" for p in test_df["priority"]], [p.priority.label == "high" for p in preds],
                     zero_division=0),
        4,
    )
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="Train and score the SentinelDesk triage model.")
    ap.add_argument("--train", action="store_true", help="fit on kb_train and save the model")
    ap.add_argument("--limit", type=int, default=None, help="train on the first N kb tickets (quick run)")
    args = ap.parse_args()

    kb, test = dataset.load_split()
    if args.limit:
        kb = kb.head(args.limit)

    if args.train or not MODEL_PATH.exists():
        print(f"training on {len(kb):,} kb_train tickets")
        t0 = time.perf_counter()
        model = TriageModel().fit(kb)
        path = model.save()
        print(f"trained in {time.perf_counter() - t0:.1f}s -> {path}")
    else:
        model = TriageModel.load()

    print(f"\nscoring on {len(test):,} holdout tickets")
    metrics = evaluate(model, test)
    print("\n=== holdout metrics ===")
    for k, v in metrics.items():
        print(f"  {k:<40} {v}")


if __name__ == "__main__":
    main()
