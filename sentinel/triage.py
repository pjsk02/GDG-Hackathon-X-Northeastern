"""Multi-task triage: type / queue / priority (+ language) with calibrated confidence.

Deliberately *not* an LLM. A linear model over TF-IDF features trains in seconds, predicts in
~1 ms, and gives a real probability from `predict_proba` — which is what the escalation gate needs.
An LLM asked for the same three labels is ~1.7 s per ticket, cannot be scored over 5.7k holdout
tickets in a hackathon, and reports confidence it has not earned. The LLM's job here is the
grounded reply, not the labels.

Word (1-2) and character (3-5) n-grams are combined: German compounds ("Zahlungsrückerstattung")
share character n-grams with their parts, so one feature space covers both languages.

Owner: B (Shishir). Contract (keep stable): `TriageModel.predict(subject, body) -> TriagePrediction`,
`predict_batch(texts)`, `get_model()`, `evaluate(model, df)`, `HeadPrediction`, `TriagePrediction`.
Added for F2 and used by sentinel/calibration.py, explain.py and feedback.py:
    TriageModel.fit(train_df)                  linear heads on the TRAIN slice
    TriageModel.calibrate(val_df)              per-head calibration on the VALIDATION slice
    TriageModel.predict_proba_heads(texts, calibrated=True) -> {head: (proba, classes)}
    TriageModel.heads[head]                    the raw LogisticRegression (coefficients for explain)

Calibration (F2). Candidates per head: temperature scaling (softmax(logits / T), one scalar, never
changes the predicted label), and scikit-learn's `CalibratedClassifierCV(FrozenEstimator(head))` with
"sigmoid" or "isotonic". Each is cross-fitted on two halves of the validation slice and the lowest
out-of-fold log-loss wins; a candidate that costs more than `MAX_F1_DROP` validation Macro-F1 is not
eligible, and "none" stays if nothing beats the raw head. On this dataset temperature wins every head:
one-vs-rest sigmoid/isotonic on ~2.3k validation tickets is worse than no calibration and flips labels.

    python -m sentinel.triage --train      # fit on train, calibrate on validation, score the holdout
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, log_loss, recall_score
from sklearn.pipeline import FeatureUnion

from sentinel import dataset

MODEL_PATH = Path("data/sentinel/triage_model.joblib")
HEADS = ("type", "queue", "priority")
CALIBRATION_METHODS = ("temperature", "sigmoid", "isotonic")
MAX_F1_DROP = 0.005  # a calibrator may not cost more validation Macro-F1 than this
CALIBRATION_SEED = 0


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
        """One number for the gate: the weaker of the two risk-bearing heads.

        Queue is deliberately excluded. It has 10 classes, so its top probability is structurally
        low (median 0.45) and thresholding on it escalates 91% of all tickets. A wrong queue is a
        routing annoyance; a wrong type or priority is a missed outage, so only those gate.
        """
        return min(self.type.confidence, self.priority.confidence)

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


# Per-head hyperparameters, chosen on the VALIDATION slice (train-slice fit, 2,287 val tickets):
#   type, queue: C=4, balanced. class_weight="balanced" matters for queue: "General Inquiry" is 1.4%
#     of the data but still has to be routable.
#   priority: C=8, no class weights. Validation Macro-F1 0.602 -> 0.620, high-priority recall
#     0.657 -> 0.691, log-loss 0.856 -> 0.864 (balanced C=32 had F1 0.626 but recall 0.672 and log-loss 0.956).
HEAD_PARAMS: dict[str, dict[str, object]] = {
    "type": {"C": 4.0, "class_weight": "balanced"},
    "queue": {"C": 4.0, "class_weight": "balanced"},
    "priority": {"C": 8.0, "class_weight": None},
}


def _classifier(head: str = "type") -> LogisticRegression:
    return LogisticRegression(max_iter=1500, **HEAD_PARAMS.get(head, HEAD_PARAMS["type"]))


class TriageModel:
    """One shared feature space, one linear head per target, plus a character-level language head."""

    def __init__(self) -> None:
        self.vectorizer = _vectorizer()
        self.heads: dict[str, LogisticRegression] = {}
        self.lang_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3), max_features=20_000)
        self.lang_head: LogisticRegression | None = None
        self.trained_on = 0
        # head -> float T (temperature) or a fitted CalibratedClassifierCV. Missing head = uncalibrated.
        self.calibrators: dict[str, Any] = {}
        self.calibration_method: dict[str, str] = {}
        self.calibration_selection: dict[str, dict[str, dict[str, float]]] = {}
        self.calibrated_on = 0

    @property
    def is_calibrated(self) -> bool:
        return bool(self.calibrators)

    @property
    def classes(self) -> dict[str, list[str]]:
        return {head: [str(c) for c in clf.classes_] for head, clf in self.heads.items()}

    # -- training ---------------------------------------------------------

    def fit(self, kb_train_df: pd.DataFrame, verbose: bool = True) -> "TriageModel":
        texts = [dataset.ticket_text(r) for r in kb_train_df.to_dict("records")]
        t0 = time.perf_counter()
        X = self.vectorizer.fit_transform(texts)
        if verbose:
            print(f"  features: {X.shape[1]:,} ({time.perf_counter() - t0:.1f}s)", flush=True)
        for head in HEADS:
            t = time.perf_counter()
            clf = _classifier(head)
            clf.fit(X, kb_train_df[head].astype(str))
            self.heads[head] = clf
            if verbose:
                print(f"  {head:<9} {len(clf.classes_)} classes  ({time.perf_counter() - t:.1f}s)", flush=True)
        t = time.perf_counter()
        Xl = self.lang_vectorizer.fit_transform(texts)
        self.lang_head = LogisticRegression(max_iter=1000).fit(Xl, kb_train_df["language"].astype(str))
        if verbose:
            print(f"  language  {len(self.lang_head.classes_)} classes  ({time.perf_counter() - t:.1f}s)", flush=True)
        self.trained_on = len(kb_train_df)
        return self

    # -- calibration (F2) ---------------------------------------------------

    def calibrate(self, val_df: pd.DataFrame, methods: tuple[str, ...] = CALIBRATION_METHODS,
                  verbose: bool = True) -> "TriageModel":
        """Pick and fit one calibrator per head on the VALIDATION slice (never the holdout)."""
        texts = [dataset.ticket_text(r) for r in val_df.to_dict("records")]
        X_all = self.vectorizer.transform(texts)
        order = np.random.default_rng(CALIBRATION_SEED).permutation(X_all.shape[0])
        self.calibrators, self.calibration_method, self.calibration_selection = {}, {}, {}

        for head in HEADS:
            clf = self.heads[head]
            y_all = val_df[head].astype(str).to_numpy()
            # A label never seen in training cannot be calibrated; drop those rows for this head.
            keep = order[np.isin(y_all[order], clf.classes_.astype(str))]
            X, y = X_all[keep], y_all[keep]
            halves = np.array_split(np.arange(len(y)), 2)

            stats: dict[str, dict[str, float]] = {}
            for method in ("none", *methods):
                oof = np.zeros((len(y), len(clf.classes_)))
                try:
                    for a, b in ((halves[0], halves[1]), (halves[1], halves[0])):
                        oof[b] = _calibrated_proba(clf, _fit_calibrator(clf, method, X[a], y[a]), X[b])
                except Exception as exc:  # e.g. isotonic on a tiny slice: skip that candidate
                    if verbose:
                        print(f"  {head:<9} {method:<11} skipped: {type(exc).__name__}: {exc}", flush=True)
                    continue
                stats[method] = {
                    "log_loss": round(float(log_loss(y, np.clip(oof, 1e-12, 1.0), labels=clf.classes_)), 4),
                    "macro_f1": round(float(f1_score(y, clf.classes_[oof.argmax(1)], average="macro",
                                                     zero_division=0)), 4),
                }

            floor = stats["none"]["macro_f1"] - MAX_F1_DROP
            eligible = {m: v for m, v in stats.items() if v["macro_f1"] >= floor}
            best = min(eligible, key=lambda m: (eligible[m]["log_loss"], m != "none"))
            self.calibration_selection[head] = stats
            self.calibration_method[head] = best
            if best != "none":
                self.calibrators[head] = _fit_calibrator(clf, best, X, y)
            if verbose:
                line = "  ".join(f"{m} {v['log_loss']:.4f}" for m, v in stats.items())
                extra = f" (T={self.calibrators[head]:.3f})" if best == "temperature" else ""
                print(f"  {head:<9} val log-loss  {line}  -> {best}{extra}", flush=True)

        self.calibrated_on = int(len(val_df))
        return self

    def predict_proba_heads(self, texts: list[str], calibrated: bool = True) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """{head: (probabilities [n, k], classes [k])}; the raw head output when `calibrated=False`."""
        X = self.vectorizer.transform(texts)
        out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for head in HEADS:
            clf = self.heads[head]
            cal = self.calibrators.get(head) if calibrated else None
            out[head] = (_calibrated_proba(clf, cal, X), clf.classes_)
        return out

    # -- inference --------------------------------------------------------

    def predict_batch(self, texts: list[str]) -> list[TriagePrediction]:
        t0 = time.perf_counter()
        per_head = self.predict_proba_heads(texts, calibrated=True)
        Xl = self.lang_vectorizer.transform(texts)
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
        # Pickle the parts, not `self`: `python -m sentinel.triage` would otherwise bake a
        # `__main__.TriageModel` reference into the file that no importing process can resolve.
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "vectorizer": self.vectorizer,
                "heads": self.heads,
                "lang_vectorizer": self.lang_vectorizer,
                "lang_head": self.lang_head,
                "trained_on": self.trained_on,
                "calibrated": self.is_calibrated,
                "calibrators": self.calibrators,
                "calibration_method": self.calibration_method,
                "calibration_selection": self.calibration_selection,
                "calibrated_on": self.calibrated_on,
                "classes": self.classes,
                "sklearn_version": sklearn.__version__,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            path,
            compress=3,
        )
        return path

    @staticmethod
    def load(path: Path | str = MODEL_PATH) -> "TriageModel":
        parts = joblib.load(path)
        model = TriageModel()
        model.vectorizer = parts["vectorizer"]
        model.heads = parts["heads"]
        model.lang_vectorizer = parts["lang_vectorizer"]
        model.lang_head = parts["lang_head"]
        model.trained_on = parts.get("trained_on", 0)
        # Models saved before F2 have no calibration keys and load as uncalibrated.
        model.calibrators = parts.get("calibrators", {})
        model.calibration_method = parts.get("calibration_method", {})
        model.calibration_selection = parts.get("calibration_selection", {})
        model.calibrated_on = parts.get("calibrated_on", 0)
        return model

    def metadata(self) -> dict[str, object]:
        return {
            "trained_on": self.trained_on,
            "calibrated": self.is_calibrated,
            "calibrated_on": self.calibrated_on,
            "calibration_method": dict(self.calibration_method),
            "temperatures": {h: round(c, 4) for h, c in self.calibrators.items() if isinstance(c, float)},
            "classes": self.classes,
        }


def _fit_calibrator(clf: LogisticRegression, method: str, X: Any, y: np.ndarray) -> Any:
    """None for "none", a float T for "temperature", else a fitted CalibratedClassifierCV."""
    if method == "none":
        return None
    if method == "temperature":
        z = _logits(clf, X)
        yi = np.searchsorted(clf.classes_, y)
        rows = np.arange(len(yi))

        def nll(t: float) -> float:
            return float(-np.log(softmax(z / t, axis=1)[rows, yi] + 1e-12).mean())

        return float(minimize_scalar(nll, bounds=(0.05, 20.0), method="bounded").x)
    if method in ("sigmoid", "isotonic"):
        return CalibratedClassifierCV(FrozenEstimator(clf), method=method).fit(X, y)
    raise ValueError(f"unknown calibration method {method!r}")


def _logits(clf: LogisticRegression, X: Any) -> np.ndarray:
    z = clf.decision_function(X)
    return np.column_stack([np.zeros_like(z), z]) if z.ndim == 1 else z  # binary -> 2 columns


def _calibrated_proba(clf: LogisticRegression, cal: Any, X: Any) -> np.ndarray:
    if cal is None:
        return clf.predict_proba(X)
    if isinstance(cal, float):
        return softmax(_logits(clf, X) / cal, axis=1)
    return cal.predict_proba(X)


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
    ap = argparse.ArgumentParser(description="Train, calibrate and score the SentinelDesk triage model.")
    ap.add_argument("--train", action="store_true", help="fit on the train slice, calibrate on validation, save")
    ap.add_argument("--limit", type=int, default=None, help="train on the first N train tickets (quick run)")
    ap.add_argument("--no-calibrate", action="store_true", help="skip calibration (raw logistic heads)")
    args = ap.parse_args()

    train, val, test = dataset.load_train_val_test()
    if args.limit:
        train = train.head(args.limit)

    if args.train or not MODEL_PATH.exists():
        print(f"training on {len(train):,} train-slice tickets (validation {len(val):,} kept for calibration)")
        t0 = time.perf_counter()
        model = TriageModel().fit(train)
        if not args.no_calibrate:
            print(f"calibrating on {len(val):,} validation tickets")
            model.calibrate(val)
        path = model.save()
        print(f"trained in {time.perf_counter() - t0:.1f}s -> {path}")
    else:
        model = TriageModel.load()
    meta = model.metadata()
    print("model:", {k: v for k, v in meta.items() if k != "classes"})

    print(f"\nscoring on {len(test):,} holdout tickets")
    metrics = evaluate(model, test)
    print("\n=== holdout metrics ===")
    for k, v in metrics.items():
        print(f"  {k:<40} {v}")

    # Calibration on the holdout: evaluation only, it scores probabilities the model already produced.
    from sentinel import calibration

    rep = calibration.write(model, test, split="holdout")
    print(f"\n=== holdout calibration (top-label ECE, 10 bins) -> {calibration.JSON_PATH} ===")
    for head, h in rep["heads"].items():
        after = f"{h['calibrated']['ece']:.4f}" if h["calibrated"] else "n/a"
        method = meta["calibration_method"].get(head, "none")
        print(f"  {head:<9} before {h['uncalibrated']['ece']:.4f}  after {after}  ({method})")


if __name__ == "__main__":
    main()
