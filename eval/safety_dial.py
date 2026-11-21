"""Safety dial (N2): how much human workload buys how much high-priority-incident recall.

Owner: A (Je).   Run: `make dial`  (= python -m eval.safety_dial)

On the VALIDATION slice only (same signals as eval/tune_thresholds.py: train-only triage model, index
self-hit excluded, tiers from escalation.decide_tier). It sweeps the threshold grid and keeps the Pareto
frontier (no other point has a lower on-call rate AND a higher HPI recall), sorted from lenient to strict.
Each frontier point is one position of the dial.

Output (owner E's manager page reads this exact shape):
    data/eval/safety_dial.json
        {"generated_at": "...", "split": "validation",
         "points": [{"triage_confidence_min", "high_priority_alert_probability", "retrieval_similarity_min",
                     "oncall_rate", "review_rate", "auto_rate", "hpi_recall"}, ...],
         "chosen": {...same keys...}}
    data/eval/safety_dial.png   HPI recall against on-call workload, with the chosen and default points.

"chosen" is the point in data/sentinel/thresholds.json (written by `make tune`) evaluated here; if that file is
missing, the dial picks it with the same objective (lowest on-call rate with HPI recall >= 0.90).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from eval import tune_thresholds as tt
from sentinel import thresholds

DIAL_JSON = Path("data/eval/safety_dial.json")
DIAL_PNG = Path("data/eval/safety_dial.png")
POINT_KEYS = ("triage_confidence_min", "high_priority_alert_probability", "retrieval_similarity_min",
              "oncall_rate", "review_rate", "auto_rate", "hpi_recall")
MAX_POINTS = 40

# Reference chart palette (dataviz skill, light surface)
SURFACE, INK, INK_2, GRID, SERIES_1 = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"


def as_point(row: dict) -> dict:
    """Exactly the keys owner E reads, rounded."""
    return {k: round(float(row[k]), 4) for k in POINT_KEYS}


def frontier(points: pd.DataFrame, max_points: int = MAX_POINTS) -> pd.DataFrame:
    """Pareto frontier on (low oncall_rate, high hpi_recall), lenient -> strict; thinned to max_points."""
    ranked = points.sort_values(["oncall_rate", "hpi_recall", "escalation_rate"], ascending=[True, False, True])
    keep, best = [], -1.0
    for idx, row in ranked.iterrows():
        if row["hpi_recall"] > best:
            keep.append(idx)
            best = row["hpi_recall"]
    front = ranked.loc[keep].reset_index(drop=True)
    if len(front) > max_points:  # keep both ends, thin the middle evenly
        step = (len(front) - 1) / (max_points - 1)
        front = front.iloc[sorted({round(i * step) for i in range(max_points)})].reset_index(drop=True)
    return front


def chosen_point(signals: pd.DataFrame, points: pd.DataFrame, path: Path = thresholds.THRESHOLDS_PATH) -> tuple[dict, str]:
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if all(k in saved for k in tt.KEYS):
            return tt.evaluate_point(signals, saved["triage_confidence_min"], saved["high_priority_alert_probability"],
                                     saved["retrieval_similarity_min"]), str(path)
    best, _ = tt.choose(points)
    return best, "dial objective (thresholds.json missing)"


def build_dial(signals: pd.DataFrame, grid: dict | None = None,
               thresholds_path: Path = thresholds.THRESHOLDS_PATH) -> tuple[dict, pd.DataFrame, dict, str]:
    """Returns (dial_json, frontier_df, chosen_full_metrics, chosen_source)."""
    points = tt.sweep(signals, grid or tt.build_grid(signals))
    front = frontier(points)
    chosen, source = chosen_point(signals, points, thresholds_path)
    dial = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": "validation",
        "points": [as_point(r) for r in front.to_dict("records")],
        "chosen": as_point(chosen),
    }
    return dial, front, chosen, source


def plot(dial: dict, baseline: dict | None, path: Path = DIAL_PNG) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs = [p["oncall_rate"] * 100 for p in dial["points"]]
    ys = [p["hpi_recall"] * 100 for p in dial["points"]]
    c = dial["chosen"]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.axhline(90, color=INK_2, lw=1, ls=(0, (4, 3)), zorder=1)
    ax.text(xs[0] if xs else 0, 90.6, "target: 90% recall", color=INK_2, fontsize=9, va="bottom")
    ax.plot(xs, ys, color=SERIES_1, lw=2, marker="o", ms=4, zorder=2)

    def mark(p, label, filled):
        x, y = p["oncall_rate"] * 100, p["hpi_recall"] * 100
        ax.scatter([x], [y], s=90, zorder=4, edgecolors=SURFACE if filled else INK_2, linewidths=2,
                   facecolors=SERIES_1 if filled else SURFACE)
        # chosen above-left of its marker, defaults below-right, so the two never collide
        ax.annotate(label, (x, y), xytext=(-12, 12) if filled else (12, -16), textcoords="offset points",
                    ha="right" if filled else "left", fontsize=9, color=INK,
                    bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": "none", "alpha": 0.9})

    if baseline:
        mark(baseline, f"defaults ({baseline['oncall_rate']:.0%} on-call, {baseline['hpi_recall']:.1%} recall)", False)
    mark(c, f"chosen ({c['oncall_rate']:.0%} on-call, {c['hpi_recall']:.1%} recall)", True)

    ax.set_title("Safety dial: high-priority-incident recall vs on-call workload (validation)",
                 color=INK, fontsize=11, loc="left")
    ax.set_xlabel("Tickets paged to on-call (%)", color=INK_2)
    ax.set_ylabel("High-priority incidents caught (%)", color=INK_2)
    ax.grid(color=GRID, lw=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def main(argv: Iterable[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="Safety dial sweep on the validation slice.")
    ap.add_argument("--model", default=None, help="load a TRAIN-ONLY TriageModel joblib instead of fitting one")
    ap.add_argument("--out", default=str(DIAL_JSON))
    ap.add_argument("--png", default=str(DIAL_PNG))
    args = ap.parse_args(list(argv) if argv is not None else None)

    t0 = time.perf_counter()
    train_df, val_df = tt.load_train_val()
    print(f"train {len(train_df):,} / validation {len(val_df):,} (holdout not read)")
    model, _ = tt._load_model(args.model, train_df)
    store = tt._open_store()
    signals = tt.compute_signals(model, store, val_df)

    dial, front, chosen, source = build_dial(signals)
    from shared.settings import Settings
    d = Settings()
    baseline = tt.evaluate_point(signals, d.triage_confidence_min, d.high_priority_alert_probability,
                                 d.retrieval_similarity_min)

    print(f"\nfrontier: {len(dial['points'])} dial positions (chosen from {source})")
    fmt = "  {:>8} {:>12} {:>8} {:>7} {:>7} {:>7} {:>9} {:>10}"
    print(fmt.format("conf_min", "p_high_alert", "sim_min", "oncall", "review", "auto", "escalate", "hpi_recall"))
    for r in front.to_dict("records"):
        print(fmt.format(*[f"{r[k]:.3f}" for k in (*tt.KEYS[:1], "high_priority_alert_probability",
                                                   "retrieval_similarity_min", "oncall_rate", "review_rate",
                                                   "auto_rate", "escalation_rate", "hpi_recall")]))
    print(f"  chosen: {dial['chosen']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dial, indent=2), encoding="utf-8")
    png = plot(dial, baseline, Path(args.png))
    print(f"\nwritten {out} and {png}  ({time.perf_counter() - t0:.0f}s)")
    return dial


if __name__ == "__main__":
    main()
