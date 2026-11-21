"""Tune the gate thresholds on the VALIDATION slice (fix F1: never tune on the holdout).

Owner: A (Je).   Run: `make tune`  (= python -m eval.tune_thresholds)

What it does
    1. Reads ONLY data/sentinel/kb_train.csv and cuts it into (train, validation) with
       sentinel.dataset.split_train_val. The holdout file is never opened.
    2. Trains a TriageModel on the train slice in memory (or loads --model PATH, e.g. a train-only model
       from owner B) and predicts the validation slice.
    3. Top retrieval similarity per validation ticket from the real index, skipping the ticket itself:
       the index holds all of kb_train (validation included), so the self-hit is dropped (search k+1).
    4. Sweeps triage_confidence_min x high_priority_alert_probability x retrieval_similarity_min.
       Each ticket's fired rules (R1-R5) go through escalation.decide_tier, so the tiers follow owner E's
       mapping as soon as it is merged (until then every escalation counts as on-call).
    5. Objective: high-priority-incident (HPI) recall >= --target-recall (0.90) with the lowest on-call
       rate. Ties: higher recall, then lower escalation rate. If no point reaches the target, the
       highest-recall point is chosen and the JSON says so.
    6. Writes data/sentinel/thresholds.json (the three keys sentinel.thresholds.load reads, plus the
       validation metrics) and prints a table.

Not simulated: R6 (post-draft grounding) and R7 (injection) need a draft or a detector run; they can only add
escalations, so the recall here is a floor and the on-call rate a lower bound for those rules.

Reusable API (eval/safety_dial.py builds on it):
    load_train_val() -> (train_df, val_df)
    compute_signals(model, store, val_df) -> pd.DataFrame      one row per validation ticket
    evaluate_point(signals, triage_confidence_min, high_priority_alert_probability,
                   retrieval_similarity_min) -> dict           rates + hpi_recall
    sweep(signals, grid) -> pd.DataFrame
    choose(points, target_recall) -> (dict, bool)              chosen point, target_met
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from sentinel import dataset, escalation, thresholds

KEYS = thresholds.KEYS  # ("triage_confidence_min", "retrieval_similarity_min", "high_priority_alert_probability")
RULES = ("R1", "R2", "R3", "R4", "R5")
TARGET_RECALL = 0.90

DEFAULT_GRID: dict[str, list[float]] = {
    "triage_confidence_min": [round(x, 2) for x in np.arange(0.30, 0.801, 0.05)],
    "high_priority_alert_probability": [round(x, 2) for x in np.arange(0.20, 0.701, 0.05)],
    # retrieval values are completed from the observed similarity quantiles (embedder-dependent scale)
    "retrieval_similarity_min": [0.0, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6],
}
RETRIEVAL_QUANTILES = (0.02, 0.05, 0.10, 0.20, 0.30)


# --- data --------------------------------------------------------------------------------------

def load_train_val(fraction: float = dataset.VAL_FRACTION) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(train, validation) from kb_train.csv only. Deliberately does NOT call load_split(), which also
    reads (or builds) the holdout."""
    if not dataset.KB_PATH.exists():
        raise SystemExit(f"{dataset.KB_PATH} is missing: run `make sentinel-split` first")
    kb = pd.read_csv(dataset.KB_PATH).fillna("")
    return dataset.split_train_val(kb, fraction)


def _texts(df: pd.DataFrame) -> list[str]:
    return [dataset.ticket_text(r) for r in df.to_dict("records")]


# --- signals -----------------------------------------------------------------------------------

def top_similarity_excluding_self(store, texts: list[str], ticket_ids: list[str], batch: int = 256) -> np.ndarray:
    """Best index similarity for each text, ignoring the index row with the same ticket id.

    Fast path: one batched embed + matrix product (same math as VectorStore.search). Fallback: the public
    search(k=2) and drop the self-hit.
    """
    out = np.zeros(len(texts), dtype=np.float32)
    matrix_fn = getattr(store, "_matrix", None)
    if callable(matrix_fn):
        ids, matrix = matrix_fn()
        if len(ids) and matrix.size:
            row_of = {cid: i for i, cid in enumerate(ids)}
            for start in range(0, len(texts), batch):
                q = np.asarray(store.embedder.embed(texts[start:start + batch], is_query=True), dtype=np.float32)
                scores = q @ matrix.T  # (batch, n_index)
                for j, tid in enumerate(ticket_ids[start:start + batch]):
                    own = row_of.get(str(tid))
                    if own is not None:
                        scores[j, own] = -np.inf
                out[start:start + len(q)] = np.where(np.isfinite(scores.max(axis=1)), scores.max(axis=1), 0.0)
            return out
    for i, (text, tid) in enumerate(zip(texts, ticket_ids)):
        hits = [h for h in store.search(text, k=2) if h.chunk.metadata.get("ticket_id", h.chunk.id) != str(tid)]
        out[i] = hits[0].score if hits else 0.0
    return out


def compute_signals(model, store, val_df: pd.DataFrame) -> pd.DataFrame:
    """Everything the gate needs per validation ticket, computed once so the sweep is cheap."""
    texts = _texts(val_df)
    preds = model.predict_batch(texts)
    sims = top_similarity_excluding_self(store, texts, val_df["ticket_id"].astype(str).tolist())
    return pd.DataFrame({
        "ticket_id": val_df["ticket_id"].astype(str).to_numpy(),
        "pred_type": [p.type.label for p in preds],
        "pred_priority": [p.priority.label for p in preds],
        "triage_confidence": [p.confidence for p in preds],
        "p_high": [p.priority.probabilities.get("high", 0.0) for p in preds],
        "top_similarity": sims,
        "r5": [bool(escalation.commitment_requests(t)) for t in texts],
        # labels are read only to score; never fed to the gate
        "is_hpi": ((val_df["type"].astype(str) == "Incident") & (val_df["priority"].astype(str) == "high")).to_numpy(),
    })


# --- gate simulation ---------------------------------------------------------------------------

def fired_rules(signals: pd.DataFrame, triage_confidence_min: float, high_priority_alert_probability: float,
                retrieval_similarity_min: float) -> dict[str, np.ndarray]:
    """Vectorised escalation.pre_draft_gate R1-R5 (tests check it agrees with the real gate)."""
    r1 = ((signals["pred_priority"] == "high") & (signals["pred_type"] == "Incident")).to_numpy()
    r2 = ~r1 & (signals["p_high"].to_numpy() >= high_priority_alert_probability)
    r3 = signals["triage_confidence"].to_numpy() < triage_confidence_min
    r4 = signals["top_similarity"].to_numpy() < retrieval_similarity_min
    r5 = signals["r5"].to_numpy(dtype=bool)
    return {"R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5}


_TIER_CACHE: dict[tuple[str, ...], str] = {}


def tier_for(rules: tuple[str, ...]) -> str:
    """Tier for a set of fired rule ids, via the real escalation.decide_tier."""
    if rules not in _TIER_CACHE:
        reasons = [f"{r} (threshold sweep)" for r in rules]
        _TIER_CACHE[rules] = escalation.decide_tier("ESCALATE" if reasons else "AUTO_DRAFT", reasons)
    return _TIER_CACHE[rules]


def tiers(signals: pd.DataFrame, **th: float) -> np.ndarray:
    fired = fired_rules(signals, th["triage_confidence_min"], th["high_priority_alert_probability"],
                        th["retrieval_similarity_min"])
    mask = np.zeros(len(signals), dtype=np.int64)
    for bit, rule in enumerate(RULES):
        mask |= fired[rule].astype(np.int64) << bit
    by_mask = {m: tier_for(tuple(r for b, r in enumerate(RULES) if m >> b & 1)) for m in np.unique(mask)}
    return np.array([by_mask[m] for m in mask], dtype=object)


def evaluate_point(signals: pd.DataFrame, triage_confidence_min: float, high_priority_alert_probability: float,
                   retrieval_similarity_min: float) -> dict[str, float]:
    t = tiers(signals, triage_confidence_min=triage_confidence_min,
              high_priority_alert_probability=high_priority_alert_probability,
              retrieval_similarity_min=retrieval_similarity_min)
    n = max(len(t), 1)
    hpi = signals["is_hpi"].to_numpy(dtype=bool)
    oncall = t == "PAGE_ONCALL"
    review = t == "AGENT_REVIEW"
    auto = t == "AUTO_DRAFT"
    return {
        "triage_confidence_min": float(triage_confidence_min),
        "high_priority_alert_probability": float(high_priority_alert_probability),
        "retrieval_similarity_min": float(retrieval_similarity_min),
        "escalation_rate": round(float((~auto).sum()) / n, 4),
        "oncall_rate": round(float(oncall.sum()) / n, 4),
        "review_rate": round(float(review.sum()) / n, 4),
        "auto_rate": round(float(auto.sum()) / n, 4),
        "hpi_recall": round(float((oncall & hpi).sum()) / max(int(hpi.sum()), 1), 4),
        "hpi_escalated_recall": round(float((~auto & hpi).sum()) / max(int(hpi.sum()), 1), 4),
        "hpi_count": int(hpi.sum()),
        "tickets": int(len(t)),
    }


def build_grid(signals: pd.DataFrame, base: dict[str, list[float]] | None = None) -> dict[str, list[float]]:
    grid = {k: list(v) for k, v in (base or DEFAULT_GRID).items()}
    sims = signals["top_similarity"].to_numpy()
    if len(sims):
        extra = [round(float(np.quantile(sims, q)), 3) for q in RETRIEVAL_QUANTILES]
        grid["retrieval_similarity_min"] = sorted(set(grid["retrieval_similarity_min"]) | set(extra))
    return grid


def sweep(signals: pd.DataFrame, grid: dict[str, list[float]]) -> pd.DataFrame:
    rows = [
        evaluate_point(signals, c, a, s)
        for c, a, s in itertools.product(grid["triage_confidence_min"], grid["high_priority_alert_probability"],
                                         grid["retrieval_similarity_min"])
    ]
    return pd.DataFrame(rows)


def choose(points: pd.DataFrame, target_recall: float = TARGET_RECALL) -> tuple[dict, bool]:
    """Lowest on-call rate with HPI recall >= target; else the highest-recall point."""
    def clean(row: pd.Series) -> dict:
        return {k: int(v) if k in ("hpi_count", "tickets") else float(v) for k, v in row.to_dict().items()}

    feasible = points[points["hpi_recall"] >= target_recall]
    if len(feasible):
        best = feasible.sort_values(["oncall_rate", "hpi_recall", "escalation_rate"],
                                    ascending=[True, False, True]).iloc[0]
        return clean(best), True
    best = points.sort_values(["hpi_recall", "oncall_rate"], ascending=[False, True]).iloc[0]
    return clean(best), False


# --- CLI ---------------------------------------------------------------------------------------

def _load_model(model_path: str | None, train_df: pd.DataFrame):
    from sentinel.triage import TriageModel

    if model_path:
        print(f"loading train-only triage model from {model_path}")
        return TriageModel.load(model_path), f"loaded:{model_path}"
    print(f"training triage model on the TRAIN slice ({len(train_df):,} tickets, in memory)")
    return TriageModel().fit(train_df, verbose=True), f"fit-in-memory:train({len(train_df)})"


def _open_store():
    from memory.embedder import get_embedder
    from memory.store import VectorStore
    from shared.settings import get_settings

    s = get_settings()
    if not Path(s.sentinel_memory_path).exists():
        raise SystemExit(f"{s.sentinel_memory_path} is missing: run `make sentinel-index` first")
    return VectorStore(s.sentinel_memory_path, get_embedder(s))


def print_table(points: pd.DataFrame, chosen: dict, baseline: dict, top: int = 12) -> None:
    cols = ["triage_confidence_min", "high_priority_alert_probability", "retrieval_similarity_min",
            "hpi_recall", "oncall_rate", "review_rate", "auto_rate", "escalation_rate"]
    head = ["conf_min", "p_high_alert", "sim_min", "hpi_recall", "oncall", "review", "auto", "escalate"]
    fmt = "  {:>8} {:>12} {:>8} {:>10} {:>7} {:>7} {:>7} {:>8}"
    print(fmt.format(*head))

    def line(p, tag=""):
        print(fmt.format(*[f"{p[c]:.3f}" if isinstance(p[c], float) else p[c] for c in cols]) + tag)

    ranked = points.sort_values(["oncall_rate", "hpi_recall"], ascending=[True, False])
    shown = ranked[ranked["hpi_recall"] >= TARGET_RECALL].head(top)
    for _, p in shown.iterrows():
        line(p)
    print("  " + "-" * 76)
    line(baseline, "   <- settings defaults")
    line(chosen, "   <- chosen")


def main(argv: Iterable[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="Tune gate thresholds on the validation slice.")
    ap.add_argument("--model", default=None, help="load a TRAIN-ONLY TriageModel joblib instead of fitting one")
    ap.add_argument("--target-recall", type=float, default=TARGET_RECALL)
    ap.add_argument("--out", default=str(thresholds.THRESHOLDS_PATH))
    args = ap.parse_args(list(argv) if argv is not None else None)

    t0 = time.perf_counter()
    train_df, val_df = load_train_val()
    print(f"train {len(train_df):,} / validation {len(val_df):,} (holdout not read)")
    model, model_source = _load_model(args.model, train_df)
    store = _open_store()
    print(f"scoring validation: triage + retrieval (index '{store.embedder.name}', self-hit excluded)")
    signals = compute_signals(model, store, val_df)

    grid = build_grid(signals)
    points = sweep(signals, grid)
    chosen, met = choose(points, args.target_recall)

    from shared.settings import Settings
    d = Settings()
    baseline = evaluate_point(signals, d.triage_confidence_min, d.high_priority_alert_probability,
                              d.retrieval_similarity_min)

    print(f"\n{len(points)} grid points on {len(signals):,} validation tickets ({baseline['hpi_count']} HPI)")
    print_table(points, chosen, baseline)
    if not met:
        print(f"\nWARNING: no grid point reaches HPI recall {args.target_recall:.2f}; chose the highest recall.")

    out = {
        **{k: float(chosen[k]) for k in KEYS},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": "validation",
        "objective": f"min oncall_rate s.t. hpi_recall >= {args.target_recall}",
        "target_met": bool(met),
        "validation": {k: chosen[k] for k in chosen if k not in KEYS},
        "baseline_defaults": baseline,
        "tier_mapping": "escalation.decide_tier",
        "rules_simulated": list(RULES),
        "model": model_source,
        "embedder": store.embedder.name,
        "grid": grid,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print(f"\nwritten {out_path}  ({time.perf_counter() - t0:.0f}s)")
    return out


if __name__ == "__main__":
    main()
