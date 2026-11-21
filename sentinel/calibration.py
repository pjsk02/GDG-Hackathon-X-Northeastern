"""Calibration report for the triage model (F2): does "80% confident" mean right 80% of the time?

Owner: B (Shishir). Je's eval and the manager page read this module or the JSON it writes.

Contract (keep stable):
    report(model: TriageModel, df: pd.DataFrame) -> dict
    -> {"tickets": int,
        "model": {"trained_on": int, "calibrated": bool, "calibration_method": {head: str}},
        "heads": {head: {"uncalibrated": HeadCalibration, "calibrated": HeadCalibration | None}}}
       HeadCalibration = {"ece": float, "log_loss": float, "accuracy": float, "mean_confidence": float,
                          "bins": [{"lower", "upper", "count", "mean_confidence", "accuracy"}, ...10]}
    main()  ->  data/eval/calibration.json + data/eval/calibration.png

ECE is the top-label expected calibration error over 10 equal-width confidence bins:
sum over bins of |accuracy - mean confidence| x (share of tickets in the bin). 0 is perfect.

`main()` scores the HOLDOUT. This is evaluation code: it reads the holdout labels only after
prediction, to score the probabilities the model already produced. Nothing here fits anything.

    python -m sentinel.calibration                 # holdout (the honest number for the README)
    python -m sentinel.calibration --split val     # validation slice (in-sample for the calibrators)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from sentinel import dataset

N_BINS = 10
JSON_PATH = Path("data/eval/calibration.json")
PNG_PATH = Path("data/eval/calibration.png")


def reliability(proba: np.ndarray, classes: np.ndarray, y_true: np.ndarray, n_bins: int = N_BINS) -> dict[str, Any]:
    """Top-label ECE, log-loss and per-bin reliability for one head."""
    proba = np.asarray(proba, dtype=float)
    classes = np.asarray(classes)
    y_true = np.asarray(y_true).astype(str)
    if len(y_true) == 0:
        return {"ece": 0.0, "log_loss": 0.0, "accuracy": 0.0, "mean_confidence": 0.0, "bins": []}

    conf = proba.max(axis=1)
    correct = (classes[proba.argmax(axis=1)].astype(str) == y_true).astype(float)
    # Confidence 1.0 belongs in the last bin, not an 11th one.
    which = np.minimum((conf * n_bins).astype(int), n_bins - 1)

    bins: list[dict[str, Any]] = []
    ece = 0.0
    for b in range(n_bins):
        mask = which == b
        n = int(mask.sum())
        mean_conf = float(conf[mask].mean()) if n else 0.0
        acc = float(correct[mask].mean()) if n else 0.0
        if n:
            ece += abs(acc - mean_conf) * n / len(y_true)
        bins.append(
            {
                "lower": round(b / n_bins, 2),
                "upper": round((b + 1) / n_bins, 2),
                "count": n,
                "mean_confidence": round(mean_conf, 4),
                "accuracy": round(acc, 4),
            }
        )

    # Labels unseen in training cannot be scored by log-loss; drop those rows instead of crashing.
    known = np.isin(y_true, classes.astype(str))
    ll = (
        float(log_loss(y_true[known], np.clip(proba[known], 1e-12, 1.0), labels=classes.astype(str)))
        if known.any()
        else float("nan")
    )
    return {
        "ece": round(float(ece), 4),
        "log_loss": round(ll, 4),
        "accuracy": round(float(correct.mean()), 4),
        "mean_confidence": round(float(conf.mean()), 4),
        "bins": bins,
    }


def report(model: Any, df: pd.DataFrame) -> dict[str, Any]:
    """Calibration of every head, before and (if the model is calibrated) after calibration."""
    from sentinel.triage import HEADS

    texts = [dataset.ticket_text(r) for r in df.to_dict("records")]
    raw = model.predict_proba_heads(texts, calibrated=False)
    cal = model.predict_proba_heads(texts, calibrated=True) if model.is_calibrated else None

    heads: dict[str, Any] = {}
    for head in HEADS:
        y = df[head].astype(str).to_numpy()
        heads[head] = {
            "uncalibrated": reliability(*raw[head], y),
            "calibrated": reliability(*cal[head], y) if cal else None,
        }
    return {
        "tickets": len(df),
        "model": {
            "trained_on": int(model.trained_on),
            "calibrated": bool(model.is_calibrated),
            "calibration_method": dict(model.calibration_method),
        },
        "heads": heads,
    }


def plot(rep: dict[str, Any], path: Path | str = PNG_PATH) -> Path:
    """Reliability diagram, one panel per head: diagonal = perfect, bars = share of tickets per bin."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    heads = list(rep["heads"])
    fig, axes = plt.subplots(1, len(heads), figsize=(4.2 * len(heads), 4.4), sharey=True)
    for ax, head in zip(np.atleast_1d(axes), heads):
        ax.plot([0, 1], [0, 1], color="#999999", lw=1, ls="--", label="perfect")
        for key, color in (("uncalibrated", "#c2410c"), ("calibrated", "#1d4ed8")):
            h = rep["heads"][head][key]
            if not h:
                continue
            pts = [(b["mean_confidence"], b["accuracy"]) for b in h["bins"] if b["count"]]
            if pts:
                xs, ys = zip(*pts)
                ax.plot(xs, ys, marker="o", color=color, lw=1.8, label=f"{key} (ECE {h['ece']:.3f})")
        base = rep["heads"][head]["calibrated"] or rep["heads"][head]["uncalibrated"]
        total = max(sum(b["count"] for b in base["bins"]), 1)
        ax.bar([(b["lower"] + b["upper"]) / 2 for b in base["bins"]], [b["count"] / total for b in base["bins"]],
               width=1 / N_BINS * 0.9, color="#94a3b8", alpha=0.35, label="share of tickets")
        ax.set_title(head)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("predicted confidence (top label)")
        ax.legend(loc="upper left", fontsize=7.5, frameon=False)
    np.atleast_1d(axes)[0].set_ylabel("accuracy")
    fig.suptitle(f"Triage calibration on {rep.get('split', 'data')} ({rep['tickets']:,} tickets)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def write(model: Any, df: pd.DataFrame, split: str, out: Path | str = JSON_PATH,
          png: Path | str = PNG_PATH) -> dict[str, Any]:
    """report() + JSON + reliability PNG. Returns the report."""
    rep = report(model, df)
    rep["split"] = split
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    plot(rep, png)
    return rep


def main() -> None:
    from sentinel.triage import TriageModel

    ap = argparse.ArgumentParser(description="Write the triage calibration report (JSON + reliability PNG).")
    ap.add_argument("--split", choices=["holdout", "val"], default="holdout")
    ap.add_argument("--out", type=Path, default=JSON_PATH)
    ap.add_argument("--png", type=Path, default=PNG_PATH)
    args = ap.parse_args()

    _train, val, test = dataset.load_train_val_test()
    df = test if args.split == "holdout" else val
    rep = write(TriageModel.load(), df, args.split, args.out, args.png)
    print(f"calibration on {args.split} ({rep['tickets']:,} tickets) -> {args.out}, {args.png}")
    for head, h in rep["heads"].items():
        after = f"{h['calibrated']['ece']:.4f}" if h["calibrated"] else "n/a"
        print(f"  {head:<9} ECE before {h['uncalibrated']['ece']:.4f}  after {after}"
              f"   ({rep['model']['calibration_method'].get(head, 'none')})")


if __name__ == "__main__":
    main()
