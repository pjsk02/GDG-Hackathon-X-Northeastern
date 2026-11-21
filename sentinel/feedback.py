"""Learning loop: agent label corrections + champion/challenger retraining (N8).

Owner: B (Shishir). The agent panel (owner E) calls record_correction; the manager page calls
retrain_challenger. Keep the signatures stable.

Contract:
    record_correction(c: LabelCorrection) -> None
    list_corrections() -> list[LabelCorrection]
    retrain_challenger() -> dict
        -> {"status": "promoted" | "kept_champion" | "not_implemented" | "error",
            "champion": {"type_macro_f1": ..., "queue_macro_f1": ..., "priority_macro_f1": ...,
                         "hpi_recall": ..., "validation_tickets": ...} | None,
            "challenger": {...same keys...} | None,
            "corrections_used": int, "message": str,
            # extras: "corrections_skipped", "skipped_reasons", "heads_retrained", "backup_path",
            #         "duration_s", "cached" (True: nothing new, nothing trained), "last_result"}

How retrain_challenger works (never reads the holdout; only kb_train.csv is opened):
 1. Clean the corrections: map the label to a known class (case-insensitive, so "High" -> "high"),
    drop unknown labels, no-op corrections (corrected == predicted), empty text, and exact copies of
    a VALIDATION ticket (training on one would inflate the challenger's score). Latest wins per
    (ticket, head).
 2. Challenger = champion with only the CORRECTED heads refit on the train slice + corrections
    (each correction weighted CORRECTION_WEIGHT). The champion's vocabulary is reused and each refit
    is warm-started from the champion's coefficients: the same convex objective, reached in seconds
    instead of minutes. Then it is recalibrated on validation.
 3. Score both on the VALIDATION slice. Promote only if type Macro-F1, priority Macro-F1 and
    high-priority-incident recall do not drop and queue Macro-F1 drops by at most QUEUE_TOLERANCE.
 4. On promotion: back the old model up (the newest BACKUPS_KEPT are kept), save atomically, update
    the in-memory model that the pipeline already holds, and reset `triage._CACHED` so the next
    get_model() loads the new file.
 5. Remember the result. A second click with no new corrections returns at once with "kept_champion",
    "cached": True and the earlier verdict in "last_result", instead of retraining. Only one retrain
    runs at a time; it never raises.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy.sparse as sp

from sentinel import dataset, triage
from shared.contracts import LabelCorrection
from shared.settings import get_settings

CORRECTION_WEIGHT = 5.0  # one agent correction counts like 5 dataset tickets
BACKUPS_KEPT = 3
METRIC_KEYS = ("type_macro_f1", "queue_macro_f1", "priority_macro_f1", "hpi_recall")
# Promotion gate. These may not drop at all (the plan's rule; type and priority drive the safety gate):
GATED_METRICS = ("type_macro_f1", "priority_macro_f1", "hpi_recall")
# Queue only routes, so it is reported, with a guard rail: about 3 validation tickets in a small class.
QUEUE_TOLERANCE = 0.005

_LOCK = threading.Lock()


def record_correction(c: LabelCorrection) -> None:
    path = get_settings().corrections_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not c.created_at:
        c.created_at = time.time()
    with path.open("a", encoding="utf-8") as f:
        f.write(c.model_dump_json() + "\n")


def list_corrections() -> list[LabelCorrection]:
    path = get_settings().corrections_path
    if not path.exists():
        return []
    out: list[LabelCorrection] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(LabelCorrection.model_validate(json.loads(line)))
            except Exception:  # one bad line must not hide the others
                continue
    return out


def retrain_challenger() -> dict:
    return run_retrain(list_corrections(), model_path=triage.MODEL_PATH, kb_path=dataset.KB_PATH)


# -- implementation -------------------------------------------------------------------------


def run_retrain(
    corrections: list[LabelCorrection],
    model_path: Path | str,
    kb_path: Path | str | None = None,
    kb_df: pd.DataFrame | None = None,
    weight: float = CORRECTION_WEIGHT,
) -> dict[str, Any]:
    """retrain_challenger() with explicit inputs (tests pass a tiny kb_df and a tmp model_path)."""
    t0 = time.perf_counter()
    if not _LOCK.acquire(blocking=False):
        return _result("error", message="A retrain is already running; try again when it finishes.")
    try:
        return _run(corrections, Path(model_path), kb_path, kb_df, weight, t0)
    except Exception as exc:  # the manager page shows the message; it must never crash the app
        return _result("error", message=f"Retrain failed: {type(exc).__name__}: {exc}",
                       duration_s=round(time.perf_counter() - t0, 1))
    finally:
        _LOCK.release()


def _run(corrections, model_path: Path, kb_path, kb_df, weight: float, t0: float) -> dict[str, Any]:
    if not model_path.exists():
        return _result("error", message=f"No trained model at {model_path}. Run `make sentinel-train` first.")
    state_path = model_path.with_name("retrain_state.json")
    state = _read_json(state_path)
    champion = triage.TriageModel.load(model_path)

    used, skipped = clean_corrections(corrections, champion.classes)
    if not used:
        return _result("kept_champion", champion=state.get("champion"), corrections_skipped=len(skipped),
                       skipped_reasons=_reasons(skipped),
                       message="No usable corrections to learn from yet. The champion stays.")

    fingerprint = _fingerprint(used, weight, model_path)
    if state.get("fingerprint") == fingerprint and state.get("result"):
        last = state["result"]
        return _result("kept_champion", champion=state.get("champion"), corrections_used=last.get("corrections_used", 0),
                       corrections_skipped=len(skipped), skipped_reasons=_reasons(skipped), cached=True,
                       last_result=last, message=(
                           f"No new corrections since the last retrain ({state.get('updated_at', '?')}, which was "
                           f"'{last.get('status')}'). The current model stays."))

    # Data: kb_train only. The holdout file is never opened here.
    if kb_df is None:
        kb_df = pd.read_csv(kb_path or dataset.KB_PATH).astype(object).fillna("")  # = dataset.load_split
    train, val = dataset.split_train_val(kb_df)
    val_texts = {dataset.ticket_text(r) for r in val.to_dict("records")}
    kept = []
    for c in used:
        if c["text"] in val_texts:
            skipped.append((c, "copy of a validation ticket"))
        else:
            kept.append(c)
    used = kept
    if not used:
        return _result("kept_champion", champion=state.get("champion"), corrections_skipped=len(skipped),
                       skipped_reasons=_reasons(skipped),
                       message="Every correction was skipped (see skipped_reasons). The champion stays.")

    champ_metrics = score(champion, val)
    challenger, heads = build_challenger(champion, train, used, weight)
    challenger.calibrate(val, verbose=False)
    chal_metrics = score(challenger, val)

    drops = [k for k in GATED_METRICS if chal_metrics[k] < champ_metrics[k]]
    if chal_metrics["queue_macro_f1"] < champ_metrics["queue_macro_f1"] - QUEUE_TOLERANCE:
        drops.append("queue_macro_f1")
    common = dict(champion=champ_metrics, challenger=chal_metrics, corrections_used=len(used),
                  corrections_skipped=len(skipped), skipped_reasons=_reasons(skipped), heads_retrained=heads)
    if drops:
        res = _result("kept_champion", **common, message=(
            f"Challenger trained on {len(used)} correction(s) but " + ", ".join(
                f"{k} {champ_metrics[k]:.4f} -> {chal_metrics[k]:.4f}" for k in drops)
            + " dropped on validation (queue may drop by at most "
            + f"{QUEUE_TOLERANCE}). The champion stays."))
    else:
        backup = promote(challenger, model_path)
        gains = ", ".join(f"{k} {champ_metrics[k]:.4f} -> {chal_metrics[k]:.4f}" for k in METRIC_KEYS)
        res = _result("promoted", **common, backup_path=str(backup), message=(
            f"Challenger with {len(used)} correction(s) (heads: {', '.join(heads)}) promoted; the validation "
            f"gate held ({gains}). Old model backed up to {backup.name}."))
    res["duration_s"] = round(time.perf_counter() - t0, 1)

    # Remember the outcome against the model that is now live, so an unchanged second click is instant.
    new_state = {"fingerprint": _fingerprint(used, weight, model_path), "result": res,
                 "champion": chal_metrics if res["status"] == "promoted" else champ_metrics,
                 "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _write_json(state_path, new_state)
    return res


def clean_corrections(corrections: list[LabelCorrection], classes: dict[str, list[str]]
                      ) -> tuple[list[dict[str, str]], list[tuple[Any, str]]]:
    """(usable [{ticket_id, head, text, label}], skipped [(correction, reason)]). Latest wins per ticket+head."""
    lookup = {h: {c.strip().lower(): c for c in cls} for h, cls in classes.items()}
    latest: dict[tuple[str, str], tuple[float, int, dict[str, str]]] = {}
    skipped: list[tuple[Any, str]] = []
    for i, c in enumerate(corrections):
        head, text = c.head, (c.text or "").strip()
        label = lookup.get(head, {}).get((c.corrected or "").strip().lower())
        if not text:
            skipped.append((c, "empty text"))
        elif label is None:
            skipped.append((c, f"unknown {head} label {c.corrected!r}"))
        elif label.lower() == (c.predicted or "").strip().lower():
            skipped.append((c, "no change (corrected == predicted)"))
        else:
            key = (c.ticket_id or text, head)
            row = {"ticket_id": c.ticket_id, "head": head, "text": text, "label": label}
            if key not in latest:
                latest[key] = (c.created_at, i, row)
            elif (c.created_at, i) >= latest[key][:2]:
                skipped.append((latest[key][2], "superseded by a later correction"))
                latest[key] = (c.created_at, i, row)
            else:
                skipped.append((row, "superseded by a later correction"))
    used = [v[2] for v in sorted(latest.values(), key=lambda v: (v[0], v[1]))]
    return used, skipped


def build_challenger(champion: triage.TriageModel, train: pd.DataFrame, used: list[dict[str, str]],
                     weight: float) -> tuple[triage.TriageModel, list[str]]:
    """Champion copy with only the corrected heads refit (warm start) on train + weighted corrections.

    Memory: one sparse matrix [train | correction texts] is shared by every refit head (about 300 MB for
    the full train slice, freed afterwards). A correction row counts only for its own head; for the
    other heads it carries weight 0 and the champion's own label, so it changes nothing there.
    """
    challenger = triage.TriageModel()
    challenger.vectorizer = champion.vectorizer  # same vocabulary: features stay comparable
    challenger.lang_vectorizer, challenger.lang_head = champion.lang_vectorizer, champion.lang_head
    challenger.heads = dict(champion.heads)
    heads = sorted({c["head"] for c in used}, key=triage.HEADS.index)

    texts = list(dict.fromkeys(c["text"] for c in used))  # each correction text once, in order
    X_corr = champion.vectorizer.transform(texts)
    X_train = champion.vectorizer.transform([dataset.ticket_text(r) for r in train.to_dict("records")])
    X = sp.vstack([X_train, X_corr], format="csr")
    del X_train
    for head in heads:
        wanted = {c["text"]: c["label"] for c in used if c["head"] == head}
        own = champion.heads[head].predict(X_corr)  # placeholder label for rows that are not this head's
        y_corr = np.array([wanted.get(t, own[i]) for i, t in enumerate(texts)], dtype=object)
        w_corr = np.array([float(weight) if t in wanted else 0.0 for t in texts])
        y = np.concatenate([train[head].astype(str).to_numpy(dtype=object), y_corr])
        w = np.concatenate([np.ones(len(train)), w_corr])
        clf = copy.deepcopy(champion.heads[head])
        clf.set_params(warm_start=True)
        clf.fit(X, y, sample_weight=w)
        clf.set_params(warm_start=False)
        challenger.heads[head] = clf
    del X

    challenger.trained_on = len(train) + len(used)
    challenger.corrections_used = len(used)
    return challenger, heads


def score(model: triage.TriageModel, val: pd.DataFrame) -> dict[str, float]:
    """The promotion metrics on the VALIDATION slice."""
    m = triage.evaluate(model, val, verbose=False)
    return {
        "type_macro_f1": float(m["type_macro_f1"]),
        "queue_macro_f1": float(m["queue_macro_f1"]),
        "priority_macro_f1": float(m["priority_macro_f1"]),
        "hpi_recall": float(m["high_priority_incident_recall"]),
        "validation_tickets": int(len(val)),
    }


def promote(challenger: triage.TriageModel, model_path: Path) -> Path:
    """Back up the champion, write the challenger atomically, and make the running app use it."""
    now = time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1e6) % 1_000_000:06d}"
    backup = model_path.with_name(f"{model_path.stem}.backup-{stamp}{model_path.suffix}")
    shutil.copy2(model_path, backup)
    tmp = model_path.with_name(model_path.name + ".tmp")
    try:
        challenger.save(tmp)
        os.replace(tmp, model_path)
    except BaseException:
        tmp.unlink(missing_ok=True)  # the champion file is untouched; leave no half-written file behind
        raise
    for old in sorted(model_path.parent.glob(f"{model_path.stem}.backup-*{model_path.suffix}"))[:-BACKUPS_KEPT]:
        old.unlink(missing_ok=True)

    if Path(model_path).resolve() == Path(triage.MODEL_PATH).resolve():
        live = triage._CACHED
        if live is not None:
            # SentinelAgent keeps its own reference to this object, so update it in place. Same vectorizer,
            # so a prediction running right now sees either the old or the new heads, both valid.
            live.calibrators = challenger.calibrators
            live.calibration_method = challenger.calibration_method
            live.calibration_selection = challenger.calibration_selection
            live.heads = challenger.heads
            live.trained_on, live.corrections_used = challenger.trained_on, challenger.corrections_used
        triage._CACHED = None  # the next get_model() loads the promoted file
    return backup


# -- helpers --------------------------------------------------------------------------------


def _fingerprint(used: list[dict[str, str]], weight: float, model_path: Path) -> str:
    st = model_path.stat()
    payload = json.dumps([sorted((c["head"], c["text"], c["label"]) for c in used), weight, GATED_METRICS,
                          QUEUE_TOLERANCE, st.st_size, st.st_mtime_ns], ensure_ascii=False)  # gate change -> rerun
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reasons(skipped: list[tuple[Any, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, reason in skipped:
        out[reason] = out.get(reason, 0) + 1
    return out


def _result(status: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"status": status, "champion": None, "challenger": None, "corrections_used": 0,
                            "message": "", "corrections_skipped": 0, "skipped_reasons": {},
                            "heads_retrained": [], "cached": False}
    base.update(kw)
    return base


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # losing the cache only costs a retrain next time
