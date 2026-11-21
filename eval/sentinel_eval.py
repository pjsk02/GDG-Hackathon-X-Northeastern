"""SentinelDesk holdout evaluation.

Owner: A (Je).

Four things are measured, in this order, because they answer different judge questions:

  1. Triage      - the full 5,718-ticket holdout, Macro-F1 per head + High-Priority Incident Recall.
                   Labels are read only to score predictions that were made from raw text.
                   + calibration (owner B's sentinel/calibration.py `report(model, df)`, skipped if absent).
  2. End to end  - a sample of unseen holdout tickets through the whole pipeline: groundedness,
                   citation rejection rate, escalation rate, tier rates (auto-draft / agent review /
                   on-call), guard findings per ticket, injection hits, language match, p50/p95 latency.
  3. Behaviour   - hand-written adversarial and routine cases from eval/sentinel_cases.jsonl and owner D's
                   eval/cases_guardrails.jsonl (if present). Optional expectations per case:
                       expect_escalation          true/false/null
                       expect_tier_not            list of tiers the case must not get, e.g. ["PAGE_ONCALL"]
                       expect_precedent_language  language of the top precedent, e.g. "en" (cross-lingual)
                       expect_guard_safe          true: an unbacked number in the draft must not auto-send
  4. Leakage     - the index holds kb_train ids only, no holdout id.

Everything is written to data/eval/sentinel-<timestamp>/ (JSON + CSV + chart.png) and report.json is always
also copied to data/eval/latest/report.json (stable path for the manager page and the README).
Every run also rebuilds docs/demo/eval_report.html, one offline page with charts of all of the above plus the
safety dial (data/eval/safety_dial.json), tuned thresholds and calibration (data/eval/calibration.json).

    python -m eval.sentinel_eval                          # 120 holdout tickets, default provider
    python -m eval.sentinel_eval --sample 20 --compare extractive
    python -m eval.sentinel_eval --compare gemini extractive
    python -m eval.sentinel_eval --triage-only            # seconds, no LLM
    python -m eval.sentinel_eval --html-only              # rebuild the eval page from saved outputs
"""

from __future__ import annotations

import argparse
import html as _html
import importlib
import json
import math
import shutil
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from sentinel import dataset

OUT_ROOT = Path("data/eval")
LATEST_DIR = OUT_ROOT / "latest"
CASES = Path("eval/sentinel_cases.jsonl")
GUARDRAIL_CASES = Path("eval/cases_guardrails.jsonl")  # owner D, optional
CASE_FILES = (CASES, GUARDRAIL_CASES)
TIERS = ("AUTO_DRAFT", "AGENT_REVIEW", "PAGE_ONCALL")


# --- leakage ------------------------------------------------------------------------------------

def verify_no_leakage(kb: pd.DataFrame, test: pd.DataFrame, agent) -> dict[str, object]:
    """Judge-facing proof: no holdout ticket id is in the index, and the index only holds kb ids."""
    report = dict(dataset.leakage_report(kb, test))
    kb_ids = set(kb["ticket_id"])
    indexed = set(agent.store.sources())
    report["indexed_chunks"] = len(indexed)
    report["indexed_not_in_kb"] = len(indexed - kb_ids)
    report["holdout_ids_in_index"] = len(indexed & set(test["ticket_id"]))
    report["ok"] = bool(report["ok"]) and report["indexed_not_in_kb"] == 0 and report["holdout_ids_in_index"] == 0
    return report


# --- calibration (owner B) ----------------------------------------------------------------------

def calibration_section(model, test: pd.DataFrame, module: str = "sentinel.calibration") -> dict[str, object]:
    """Owner B's calibration numbers on the holdout, or a clean skip if sentinel/calibration.py is missing."""
    try:
        cal = importlib.import_module(module)
    except ModuleNotFoundError:
        return {"available": False, "reason": f"{module} not found (owner B has not merged it yet)"}
    report_fn = getattr(cal, "report", None)
    if not callable(report_fn):
        return {"available": False, "reason": f"{module}.report(model, df) not defined"}
    try:
        numbers = report_fn(model, test)
    except Exception as e:  # noqa: BLE001 - an add-on must never stop the evaluation
        return {"available": False, "reason": f"{module}.report failed: {str(e)[:200]}"}
    return {"available": True, "split": "holdout", **(numbers if isinstance(numbers, dict) else {"value": numbers})}


# --- per-result helpers -------------------------------------------------------------------------

def _tier(result) -> str:
    tier = getattr(result, "tier", None)
    if tier in TIERS:
        return tier
    return "AUTO_DRAFT" if result.escalation == "AUTO_DRAFT" else "PAGE_ONCALL"  # placeholder mapping


def _guard_findings(result) -> list:
    return list(getattr(result, "guard_findings", None) or [])


def _injection_flags(result) -> list[str]:
    return list(getattr(result, "injection_flags", None) or [])


def tier_rates(tiers: pd.Series) -> dict[str, float]:
    n = max(len(tiers), 1)
    return {
        "tier_auto_draft_rate": round(float((tiers == "AUTO_DRAFT").sum()) / n, 4),
        "tier_agent_review_rate": round(float((tiers == "AGENT_REVIEW").sum()) / n, 4),
        "tier_oncall_rate": round(float((tiers == "PAGE_ONCALL").sum()) / n, 4),
    }


# --- 2. end to end ------------------------------------------------------------------------------

def run_pipeline_sample(
    agent, test: pd.DataFrame, n: int, provider: str | None, seed: int = 7
) -> tuple[dict[str, object], pd.DataFrame]:
    sample = test.sample(n=min(n, len(test)), random_state=seed).reset_index(drop=True)
    rows = []
    for i, row in enumerate(sample.to_dict("records"), start=1):
        result = agent.triage(row.get("subject") or None, row["body"], provider=provider)
        top = result.precedents[0] if result.precedents else None
        findings = _guard_findings(result)
        flags = _injection_flags(result)
        rows.append(
            {
                "ticket_id": row["ticket_id"],
                "gold_type": row["type"], "pred_type": result.triage.type,
                "gold_queue": row["queue"], "pred_queue": result.triage.queue,
                "gold_priority": row["priority"], "pred_priority": result.triage.priority,
                "gold_language": row["language"], "detected_language": result.detected_language,
                "triage_confidence": result.triage.triage_confidence,
                "escalation": result.escalation,
                "tier": _tier(result),
                "escalation_reasons": " ; ".join(result.escalation_reasons),
                "grounded": result.grounded,
                "refused": result.refused,
                "n_verified": len(result.verified_citations),
                "n_rejected": len(result.rejected_citations),
                "n_guard_findings": len(findings),
                "guard_findings": " ; ".join(f"{g.kind}:{g.text}" for g in findings),
                "n_injection_flags": len(flags),
                "cited": ",".join(result.cited_ticket_ids),
                "top_similarity": result.top_similarity,
                "top_precedent": top.ticket_id if top else "",
                "top_precedent_queue": top.queue if top else "",
                "reply_chars": len(result.draft_reply or ""),
                "latency_ms": result.latency_ms,
                "generation_ms": result.stage_latency_ms.get("generation_ms", 0.0),
                "retrieval_ms": result.stage_latency_ms.get("retrieval_ms", 0.0),
                "provider": result.provider,
                "error": result.error or "",
            }
        )
        if i % 10 == 0:
            print(f"  {i}/{len(sample)}  (last {rows[-1]['latency_ms'] / 1000:.1f}s)", flush=True)

    df = pd.DataFrame(rows)
    return summarize_pipeline(df, provider or agent.settings.llm_provider), df


def summarize_pipeline(df: pd.DataFrame, provider: str) -> dict[str, object]:
    drafted = df[df["reply_chars"] > 0]
    latencies = sorted(df["latency_ms"])
    n = max(len(df), 1)
    return {
        "tickets": len(df),
        "provider": provider,
        "groundedness_rate": round(float(df["grounded"].mean()), 4),
        "grounded_of_drafted": round(float(drafted["grounded"].mean()), 4) if len(drafted) else 0.0,
        "refusal_rate": round(float(df["refused"].mean()), 4),
        "escalation_rate": round(float((df["escalation"] == "ESCALATE").mean()), 4),
        "auto_draft_rate": round(float((df["escalation"] == "AUTO_DRAFT").mean()), 4),
        **tier_rates(df["tier"]),
        "guard_findings_total": int(df["n_guard_findings"].sum()),
        "guard_findings_per_ticket": round(float(df["n_guard_findings"].sum()) / n, 4),
        "tickets_with_guard_findings": int((df["n_guard_findings"] > 0).sum()),
        "injection_hits": int((df["n_injection_flags"] > 0).sum()),
        "injection_hit_rate": round(float((df["n_injection_flags"] > 0).sum()) / n, 4),
        "citations_verified_total": int(df["n_verified"].sum()),
        "citations_rejected_total": int(df["n_rejected"].sum()),
        "citation_rejection_rate": round(
            float(df["n_rejected"].sum()) / max(int(df["n_verified"].sum() + df["n_rejected"].sum()), 1), 4),
        "language_match_rate": round(float((df["detected_language"] == df["gold_language"]).mean()), 4),
        "retrieved_queue_match_rate": round(float((df["top_precedent_queue"] == df["gold_queue"]).mean()), 4),
        "mean_top_similarity": round(float(df["top_similarity"].mean()), 4),
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
        "latency_p95_ms": round(latencies[max(int(len(latencies) * 0.95) - 1, 0)], 1) if latencies else 0.0,
        "latency_mean_ms": round(float(df["latency_ms"].mean()), 1) if len(df) else 0.0,
        "errors": int((df["error"] != "").sum()),
    }


# --- 3. behaviour cases -------------------------------------------------------------------------

def load_cases(paths: Iterable[Path] = CASE_FILES) -> list[dict]:
    """Cases from every file that exists, tagged with their source; a duplicate id gets the file stem prefixed."""
    cases, seen = [], set()
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            case["source"] = path.name
            if case["id"] in seen:
                case["id"] = f"{path.stem}:{case['id']}"
            seen.add(case["id"])
            cases.append(case)
    return cases


def check_case(case: dict, result) -> dict[str, object]:
    """Every expectation the case states, checked; `correct` is None when the case states none."""
    checks: dict[str, bool] = {}
    escalated = result.escalation == "ESCALATE"
    tier = _tier(result)
    if case.get("expect_escalation") is not None:
        checks["escalation"] = bool(escalated) == bool(case["expect_escalation"])
    if case.get("expect_tier_not"):
        checks["tier_not"] = tier not in set(case["expect_tier_not"])
    if case.get("expect_precedent_language"):
        top = result.precedents[0] if result.precedents else None
        checks["precedent_language"] = bool(top) and top.language == case["expect_precedent_language"]
    if case.get("expect_guard_safe"):
        number_findings = [g for g in _guard_findings(result) if g.kind in ("number", "money", "percent", "date")]
        checks["guard_safe"] = not (number_findings and tier == "AUTO_DRAFT")
    return {
        "escalated": escalated,
        "tier": tier,
        "checks": json.dumps(checks),
        "failed_checks": ",".join(k for k, ok in checks.items() if not ok),
        "correct": None if not checks else all(checks.values()),
    }


def run_behaviour_cases(agent, provider: str | None,
                        paths: Iterable[Path] = CASE_FILES) -> tuple[dict[str, object], pd.DataFrame]:
    rows = []
    for c in load_cases(paths):
        result = agent.triage(c.get("subject") or None, c["body"], provider=provider)
        rows.append(
            {
                "id": c["id"],
                "source": c["source"],
                "expect_escalation": c.get("expect_escalation"),
                **check_case(c, result),
                "reasons": " ; ".join(result.escalation_reasons),
                "n_guard_findings": len(_guard_findings(result)),
                "injection_flags": " ; ".join(_injection_flags(result)),
                "grounded": result.grounded,
                "refused": result.refused,
                "language": result.detected_language,
                "top_precedent_language": result.precedents[0].language if result.precedents else "",
                "pii_masked": result.pii_masked,
                "pii_found": json.dumps(result.pii_found),
                "latency_ms": result.latency_ms,
                "reply": (result.draft_reply or "")[:400],
            }
        )
    df = pd.DataFrame(rows)
    return summarize_cases(df), df


def summarize_cases(df: pd.DataFrame) -> dict[str, object]:
    if df.empty:
        return {"cases": 0}
    scored = df[df["correct"].notna()]
    adversarial = df[df["expect_escalation"] == True]  # noqa: E712
    return {
        "cases": len(df),
        "case_sources": sorted(df["source"].unique().tolist()),
        "scored_cases": len(scored),
        "behaviour_pass_rate": round(float(scored["correct"].astype(bool).mean()), 4) if len(scored) else 0.0,
        "adversarial_cases": len(adversarial),
        "adversarial_escalation_rate": round(float(adversarial["escalated"].mean()), 4) if len(adversarial) else 0.0,
        "case_injection_hits": int((df["injection_flags"] != "").sum()),
        "pii_cases_masked": int(df["pii_masked"].sum()),
        **{f"case_{k}": v for k, v in tier_rates(df["tier"]).items()},
    }


# --- output -------------------------------------------------------------------------------------

def chart(out_dir: Path, triage_metrics: dict, per_provider: dict[str, dict]) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    heads = ["type", "queue", "priority"]
    axes[0].bar(heads, [triage_metrics[f"{h}_macro_f1"] for h in heads], color="#2563eb")
    axes[0].axhline(triage_metrics["high_priority_incident_recall"], color="#dc2626", ls="--",
                    label=f"high-prio Incident recall {triage_metrics['high_priority_incident_recall']:.2f}")
    axes[0].set_ylim(0, 1); axes[0].set_title(f"Triage Macro-F1 ({triage_metrics['holdout_tickets']:,} holdout)")
    axes[0].legend(fontsize=8)

    names = list(per_provider)
    if names:
        axes[1].bar(names, [per_provider[n]["groundedness_rate"] for n in names], color="#16a34a")
        axes[1].set_ylim(0, 1); axes[1].set_title("Groundedness (≥1 verified citation)")
        axes[2].bar(names, [per_provider[n]["latency_p50_ms"] / 1000 for n in names], color="#f59e0b",
                    label="p50")
        axes[2].bar(names, [per_provider[n]["latency_p95_ms"] / 1000 for n in names], color="#fbbf24",
                    alpha=0.5, label="p95")
        axes[2].set_title("End-to-end latency (s)"); axes[2].legend(fontsize=8)
    fig.tight_layout()
    path = out_dir / "chart.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def write_report(out_dir: Path, report: dict, latest_dir: Path = LATEST_DIR) -> Path:
    """Write report.json to the timestamped run dir AND to data/eval/latest/ (stable path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, default=str)
    (out_dir / "report.json").write_text(text, encoding="utf-8")
    (latest_dir / "report.json").write_text(text, encoding="utf-8")
    return latest_dir / "report.json"


# --- HTML report page ----------------------------------------------------------------------------
# One self-contained page (docs/demo/eval_report.html) built only from the saved JSON outputs, so it
# can be regenerated in a second and opened offline during the demo. Charts are inline SVG.

HTML_OUT = Path("docs/demo/eval_report.html")
DIAL_JSON = OUT_ROOT / "safety_dial.json"
CALIBRATION_JSON = OUT_ROOT / "calibration.json"
THRESHOLDS_JSON = Path("data/sentinel/thresholds.json")
THRESHOLD_KEYS = ("triage_confidence_min", "high_priority_alert_probability", "retrieval_similarity_min")


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_report_inputs(report_path: Path = LATEST_DIR / "report.json", dial_path: Path = DIAL_JSON,
                       calibration_path: Path = CALIBRATION_JSON,
                       thresholds_path: Path = THRESHOLDS_JSON) -> dict[str, dict | None]:
    """Read every saved eval output. A missing file is None; the page then says how to produce it."""
    report = _read_json(report_path)
    calibration = _read_json(calibration_path)
    if calibration is None and report and isinstance(report.get("calibration"), dict) \
            and report["calibration"].get("heads"):
        calibration = report["calibration"]
    return {"report": report, "dial": _read_json(dial_path), "calibration": calibration,
            "thresholds": _read_json(thresholds_path)}


def staleness_notes(inputs: dict[str, dict | None]) -> list[str]:
    """Plain-language warnings when the saved outputs disagree with each other."""
    notes: list[str] = []
    rep, thr = inputs.get("report"), inputs.get("thresholds")
    if rep and thr:
        used = rep.get("thresholds") or {}
        if any(k in used and k in thr and abs(float(used[k]) - float(thr[k])) > 1e-9 for k in THRESHOLD_KEYS):
            fmt = lambda d: " / ".join(f"{float(d[k]):.2f}" for k in THRESHOLD_KEYS if k in d)  # noqa: E731
            notes.append(f"The holdout run from {rep.get('generated_at', '?')} used older gate thresholds "
                         f"({fmt(used)}) than the tuned ones now saved ({fmt(thr)}). Re-run "
                         "<code>make sentinel-eval</code> to score the holdout with the tuned gate.")
    if rep and rep.get("pipeline") and "gemini" not in rep["pipeline"]:
        notes.append("The drafted replies in this run come from the extractive fallback writer, not Gemini. "
                     "Set <code>GEMINI_API_KEY</code> and run "
                     "<code>python -m eval.sentinel_eval --compare gemini extractive</code>.")
    return notes


def _e(x: object) -> str:
    return _html.escape(str(x))


def _pct(x: object, digits: int = 1) -> str:
    return "–" if x is None else f"{100 * float(x):.{digits}f}%"


def _dec(x: object, digits: int = 3) -> str:
    return "–" if x is None else f"{float(x):.{digits}f}"


def _bar_path(x0: float, y: float, w: float, h: float) -> str:
    """Horizontal bar anchored at x0 with a 4px rounded data end."""
    r = min(4.0, h / 2, max(w, 0.0))
    x1 = x0 + max(w, 0.0)
    return (f"M{x0:.1f},{y:.1f}H{x1 - r:.1f}Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f}V{y + h - r:.1f}"
            f"Q{x1:.1f},{y + h:.1f} {x1 - r:.1f},{y + h:.1f}H{x0:.1f}Z")


def _svg_triage(tri: dict) -> str:
    heads = [("Type", "type"), ("Priority", "priority"), ("Team", "queue")]
    series = [("macro_f1", "s1", "Macro-F1"), ("accuracy", "s2", "Accuracy")]
    w, label_w, right, top, row_h, bar_h, gap = 640, 84, 52, 6, 56, 16, 3
    plot_w = w - label_w - right
    h = top + row_h * len(heads) + 26
    px = lambda v: label_w + plot_w * float(v)  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Macro-F1 and accuracy per triage head">']
    for t in (0, 0.25, 0.5, 0.75, 1):
        out.append(f'<line class="grid" x1="{px(t):.1f}" x2="{px(t):.1f}" y1="{top}" y2="{h - 22}"/>'
                   f'<text class="ax" x="{px(t):.1f}" y="{h - 6}" text-anchor="middle">{t:g}</text>')
    for i, (name, key) in enumerate(heads):
        y0 = top + i * row_h + (row_h - (2 * bar_h + gap)) / 2
        out.append(f'<text class="lb" x="{label_w - 12}" y="{y0 + bar_h + 5:.1f}" text-anchor="end">{name}</text>')
        for j, (metric, cls, mlabel) in enumerate(series):
            v = tri.get(f"{key}_{metric}")
            if v is None:
                continue
            yb = y0 + j * (bar_h + gap)
            out.append(f'<path class="{cls}" d="{_bar_path(label_w, yb, plot_w * float(v), bar_h)}" '
                       f'data-tip="{name}: {mlabel} {float(v):.3f}"/>'
                       f'<text class="vl" x="{px(v) + 6:.1f}" y="{yb + bar_h - 4:.1f}">{float(v):.3f}</text>')
    out.append("</svg>")
    return "".join(out)


def _ticks(lo: float, hi: float, step: float = 0.1) -> list[float]:
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 2) for i in range(n + 1)]


def _svg_dial(dial: dict, thr: dict | None) -> str:
    pts = sorted((p for p in dial.get("points", []) if "oncall_rate" in p and "hpi_recall" in p),
                 key=lambda p: p["oncall_rate"])
    chosen = dial.get("chosen")
    default = (thr or {}).get("baseline_defaults")
    marks = pts + [m for m in (chosen, default) if m]
    if not marks:
        return ""
    xs = [m["oncall_rate"] for m in marks]
    ys = [m["hpi_recall"] for m in marks] + [0.9]
    x_lo, x_hi = max(0.0, math.floor(min(xs) * 10 - 0.5) / 10), min(1.0, math.ceil(max(xs) * 10 + 0.5) / 10)
    y_lo, y_hi = max(0.0, math.floor(min(ys) * 10 - 0.5) / 10), min(1.0, math.ceil(max(ys) * 10 + 0.5) / 10)
    w, h, ml, mr, mt, mb = 640, 380, 56, 24, 16, 50
    px = lambda v: ml + (w - ml - mr) * (v - x_lo) / (x_hi - x_lo)  # noqa: E731
    py = lambda v: mt + (h - mt - mb) * (1 - (v - y_lo) / (y_hi - y_lo))  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Safety dial: urgent incidents caught '
           f'against the share of tickets that page on-call">']
    for t in _ticks(x_lo, x_hi):
        out.append(f'<line class="grid" x1="{px(t):.1f}" x2="{px(t):.1f}" y1="{mt}" y2="{h - mb}"/>'
                   f'<text class="ax" x="{px(t):.1f}" y="{h - mb + 18}" text-anchor="middle">{t:.0%}</text>')
    for t in _ticks(y_lo, y_hi):
        out.append(f'<line class="grid" x1="{ml}" x2="{w - mr}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                   f'<text class="ax" x="{ml - 8}" y="{py(t) + 4:.1f}" text-anchor="end">{t:.0%}</text>')
    out.append(f'<line class="target" x1="{ml}" x2="{w - mr}" y1="{py(0.9):.1f}" y2="{py(0.9):.1f}"/>'
               f'<text class="ax" x="{w - mr}" y="{py(0.9) - 6:.1f}" text-anchor="end">target 90%</text>')
    line = " ".join(f"{px(p['oncall_rate']):.1f},{py(p['hpi_recall']):.1f}" for p in pts)
    out.append(f'<polyline class="s1l" points="{line}"/>')

    def tip(p: dict, title: str) -> str:
        return _e(f"{title}: catches {p['hpi_recall']:.1%} of urgent incidents, pages on-call for "
                  f"{p['oncall_rate']:.1%} of tickets (thresholds "
                  + " / ".join(f"{float(p[k]):.2f}" for k in THRESHOLD_KEYS if k in p) + ")")

    for p in pts:
        x, y = px(p["oncall_rate"]), py(p["hpi_recall"])
        out.append(f'<circle class="s1 ring" cx="{x:.1f}" cy="{y:.1f}" r="4"/>'
                   f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="10" data-tip="{tip(p, "Setting")}"/>')
    for m, cls, title in ((default, "s2", "Old defaults"), (chosen, "s1", "Tuned gate")):
        if not m:
            continue
        x, y = px(m["oncall_rate"]), py(m["hpi_recall"])
        # The curve rises left to right, so below-right (or above-left near the right edge) stays clear of it.
        if x > ml + (w - ml - mr) * 0.7:
            anchor, dx, y1, y2 = "end", -12, y - 26, y - 12
        else:
            anchor, dx, y1, y2 = "start", 10, y + 24, y + 38
        out.append(f'<circle class="{cls} ring" cx="{x:.1f}" cy="{y:.1f}" r="7"/>'
                   f'<circle class="halo" cx="{x:.1f}" cy="{y:.1f}" r="11"/>'
                   f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="13" data-tip="{tip(m, title)}"/>'
                   f'<text class="lbs" x="{x + dx:.1f}" y="{y1:.1f}" text-anchor="{anchor}">{title}</text>'
                   f'<text class="ax" x="{x + dx:.1f}" y="{y2:.1f}" text-anchor="{anchor}">'
                   f'{m["hpi_recall"]:.1%} caught · {m["oncall_rate"]:.1%} paged</text>')
    out.append(f'<text class="lb" x="{(ml + w - mr) / 2:.1f}" y="{h - 8}" text-anchor="middle">'
               f'Share of tickets that page on-call</text>'
               f'<text class="lb" transform="translate(14 {(mt + h - mb) / 2:.1f}) rotate(-90)" '
               f'text-anchor="middle">Urgent incidents caught</text></svg>')
    return "".join(out)


def _svg_reliability(name: str, head: dict) -> str:
    w, h, ml, mr, mt, mb = 240, 230, 38, 10, 10, 34
    px = lambda v: ml + (w - ml - mr) * v  # noqa: E731
    py = lambda v: mt + (h - mt - mb) * (1 - v)  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{_e(name)} reliability diagram">']
    for t in (0, 0.5, 1):
        out.append(f'<line class="grid" x1="{px(t):.1f}" x2="{px(t):.1f}" y1="{mt}" y2="{h - mb}"/>'
                   f'<line class="grid" x1="{ml}" x2="{w - mr}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                   f'<text class="ax" x="{px(t):.1f}" y="{h - mb + 16}" text-anchor="middle">{t:g}</text>'
                   f'<text class="ax" x="{ml - 6}" y="{py(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    out.append(f'<line class="target" x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(1):.1f}" y2="{py(1):.1f}"/>')
    for variant, cls, label in (("uncalibrated", "s2", "Before"), ("calibrated", "s1", "After")):
        bins = [b for b in (head.get(variant) or {}).get("bins", []) if b.get("count")]
        if not bins:
            continue
        pts = " ".join(f"{px(b['mean_confidence']):.1f},{py(b['accuracy']):.1f}" for b in bins)
        out.append(f'<polyline class="{cls}l" points="{pts}"/>')
        for b in bins:
            x, y = px(b["mean_confidence"]), py(b["accuracy"])
            out.append(f'<circle class="{cls} ring" cx="{x:.1f}" cy="{y:.1f}" r="4"/>'
                       f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="9" data-tip="{_e(name)} {label}: '
                       f'{b["mean_confidence"]:.0%} confident, {b["accuracy"]:.0%} right ({b["count"]:,} tickets)"/>')
    out.append(f'<text class="ax" x="{(ml + w - mr) / 2:.1f}" y="{h - 4}" text-anchor="middle">confidence</text>'
               "</svg>")
    return "".join(out)


def _svg_tiers(pipeline: dict) -> str:
    tiers = [("tier_auto_draft_rate", "s1", "Auto-draft"), ("tier_agent_review_rate", "s2", "Agent review"),
             ("tier_oncall_rate", "s3", "Page on-call")]
    w, label_w, row_h, bar_h = 360, 76, 34, 18
    h = row_h * len(pipeline) + 4
    plot_w = w - label_w - 4
    out = [f'<svg class="tiers" viewBox="0 0 {w} {h}" role="img" aria-label="Where tickets went, per writer">']
    for i, (prov, s) in enumerate(pipeline.items()):
        y = 8 + i * row_h
        out.append(f'<text class="lb" x="{label_w - 12}" y="{y + bar_h - 4}" text-anchor="end">{_e(prov)}</text>')
        x = float(label_w)
        for key, cls, label in tiers:
            v = float(s.get(key) or 0)
            seg = plot_w * v
            if seg <= 0:
                continue
            out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y}" width="{max(seg - 2, 1):.1f}" height="{bar_h}" '
                       f'rx="2" data-tip="{_e(prov)}: {label} {v:.0%}"/>')
            x += seg
    out.append("</svg>")
    caption = "".join(
        f"<div><b>{_e(prov)}</b> " + " · ".join(f"{label} {float(s.get(key) or 0):.0%}" for key, _, label in tiers)
        + "</div>" for prov, s in pipeline.items())
    return "".join(out) + f'<div class="note">{caption}</div>'


def _legend(items: list[tuple[str, str]]) -> str:
    return '<div class="legend">' + "".join(
        f'<span><i class="sw {cls}"></i>{_e(label)}</span>' for cls, label in items) + "</div>"


def _missing(what: str, command: str) -> str:
    return f'<p class="missing">No {what} yet. Run <code>{_e(command)}</code>, then regenerate this page.</p>'


def _pill(ok: bool, yes: str, no: str) -> str:
    return (f'<span class="pill ok"><i aria-hidden="true">✓</i>{_e(yes)}</span>' if ok
            else f'<span class="pill bad"><i aria-hidden="true">!</i>{_e(no)}</span>')


def _section_tiles(inputs: dict) -> str:
    rep, thr = inputs.get("report") or {}, inputs.get("thresholds") or {}
    tri, leak = rep.get("triage") or {}, rep.get("leakage") or {}
    val = thr.get("validation") or {}
    pipe = rep.get("pipeline") or {}
    first = next(iter(pipe.values()), {}) if pipe else {}
    tiles = [
        ("Urgent incidents caught", _pct(val.get("hpi_recall")),
         f"Validation slice, tuned gate. Target 90%: {'met' if thr.get('target_met') else 'not met'}."),
        ("Ticket type Macro-F1", _dec(tri.get("type_macro_f1")),
         f"{tri.get('holdout_tickets', 0):,} unseen holdout tickets."),
        ("Drafts with a verified citation", _pct(first.get("groundedness_rate"), 0),
         f"{first.get('tickets', 0)} holdout tickets, {next(iter(pipe), 'no')} writer."),
        ("Holdout tickets in the index", str(leak.get("holdout_ids_in_index", "–")),
         f"Of {leak.get('indexed_chunks', 0):,} indexed past tickets."),
    ]
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div><div class="s">{_e(s)}</div></div>'
        for k, v, s in tiles) + "</div>"


def _section_triage(rep: dict) -> str:
    tri = rep.get("triage")
    if not tri:
        return _missing("holdout triage results", "make sentinel-eval")
    rows = "".join(f"<tr><td>{n}</td><td class='n'>{_dec(tri.get(f'{k}_macro_f1'))}</td>"
                   f"<td class='n'>{_pct(tri.get(f'{k}_accuracy'))}</td></tr>"
                   for n, k in (("Type", "type"), ("Priority", "priority"), ("Team", "queue")))
    return f"""
<div class="split"><div class="panel">{_legend([("s1", "Macro-F1"), ("s2", "Accuracy")])}{_svg_triage(tri)}</div>
<div class="facts"><div class="tablewrap"><table><thead><tr><th>Head</th><th class='n'>Macro-F1</th><th class='n'>Accuracy</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<dl>
<div><dt>Language detected correctly</dt><dd>{_pct(tri.get('language_accuracy'))}</dd></div>
<div><dt>Urgent incidents in the holdout</dt><dd>{tri.get('high_priority_incident_count', '–'):,}</dd></div>
<div><dt>Labelled exactly "high-priority Incident"</dt><dd>{_pct(tri.get('high_priority_incident_recall'))}</dd></div>
<div><dt>Labelled high priority (escalated)</dt><dd>{_pct(tri.get('high_priority_incident_recall_via_gate'))}</dd></div>
<div><dt>Time to classify one ticket</dt><dd>{_dec(tri.get('latency_ms_per_ticket'), 2)} ms</dd></div>
</dl></div></div>"""


def _section_dial(dial: dict | None, thr: dict | None) -> str:
    if not dial:
        return _missing("safety dial", "make tune && make dial")
    base, val = (thr or {}).get("baseline_defaults") or {}, (thr or {}).get("validation") or {}
    tuned = {**{k: (thr or {}).get(k) for k in THRESHOLD_KEYS}, **val} if thr else (dial.get("chosen") or {})
    rows = [("Triage confidence minimum", "triage_confidence_min", _dec),
            ("Urgent alert probability", "high_priority_alert_probability", _dec),
            ("Retrieval similarity minimum", "retrieval_similarity_min", _dec),
            ("Urgent incidents caught", "hpi_recall", _pct), ("Pages on-call", "oncall_rate", _pct),
            ("Sent to agent review", "review_rate", _pct), ("Auto-drafted", "auto_rate", _pct),
            ("Mistriaged tickets a human sees", "mistriage_caught", _pct)]
    body = "".join(f"<tr><td>{n}</td><td class='n'>{f(base.get(k)) if base else '–'}</td>"
                   f"<td class='n strong'>{f(tuned.get(k))}</td></tr>" for n, k, f in rows)
    tickets = val.get("tickets")
    return f"""
<div class="split"><div class="panel">{_legend([("s1", "Settings tried"), ("s2", "Old defaults")])}{_svg_dial(dial, thr)}</div>
<div class="facts"><div class="tablewrap"><table><thead><tr><th>Validation slice{f" ({tickets:,} tickets)" if tickets else ""}</th>
<th class='n'>Old defaults</th><th class='n'>Tuned</th></tr></thead><tbody>{body}</tbody></table></div>
<p class="note">Objective: {_e((thr or {}).get('objective', 'fewest on-call pages with at least 90% of urgent incidents caught'))}.</p>
</div></div>"""


def _section_calibration(cal: dict | None) -> str:
    heads = (cal or {}).get("heads") or {}
    if not heads:
        return _missing("calibration results", "make calibrate")
    names = {"type": "Type", "priority": "Priority", "queue": "Team"}
    order = [k for k in ("type", "priority", "queue") if k in heads] + [k for k in heads if k not in names]
    charts = "".join(
        f'<figure><figcaption>{_e(names.get(k, k))} <span>ECE {_dec((heads[k].get("uncalibrated") or {}).get("ece"))}'
        f' → {_dec((heads[k].get("calibrated") or {}).get("ece"))}</span></figcaption>{_svg_reliability(names.get(k, k), heads[k])}</figure>'
        for k in order)
    rows = "".join(
        f"<tr><td>{_e(names.get(k, k))}</td><td class='n'>{_dec((heads[k].get('uncalibrated') or {}).get('ece'))}</td>"
        f"<td class='n strong'>{_dec((heads[k].get('calibrated') or {}).get('ece'))}</td>"
        f"<td class='n'>{_pct((heads[k].get('calibrated') or {}).get('accuracy'))}</td></tr>" for k in order)
    return f"""
<div class="panel">{_legend([("s1", "After calibration"), ("s2", "Before calibration")])}
<div class="multiples">{charts}</div></div>
<div class="tablewrap"><table><thead><tr><th>Head ({cal.get('tickets', 0):,} {_e(cal.get('split', 'holdout'))} tickets)</th>
<th class='n'>ECE before</th><th class='n'>ECE after</th><th class='n'>Accuracy</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def _section_pipeline(rep: dict) -> str:
    pipe = rep.get("pipeline") or {}
    if not pipe:
        return _missing("end-to-end results", "make sentinel-eval")
    provs = list(pipe)
    rows = [("Tickets run end to end", "tickets", str), ("Drafts with a verified citation", "groundedness_rate", _pct),
            ("Citations verified", "citations_verified_total", str),
            ("Citations rejected", "citations_rejected_total", str),
            ("Flagged as prompt injection", "injection_hits", str),
            ("Guard findings per ticket", "guard_findings_per_ticket", lambda v: _dec(v, 2)),
            ("Reply in the customer's language", "language_match_rate", _pct),
            ("Retrieved ticket from the right team", "retrieved_queue_match_rate", _pct),
            ("Latency p50 / p95", None, None), ("Errors", "errors", str)]
    body = ""
    for name, key, f in rows:
        cells = "".join(
            f"<td class='n'>{_dec(pipe[p].get('latency_p50_ms'), 0)} / {_dec(pipe[p].get('latency_p95_ms'), 0)} ms</td>"
            if key is None else f"<td class='n'>{f(pipe[p][key]) if pipe[p].get(key) is not None else '–'}</td>"
            for p in provs)
        body += f"<tr><td>{name}</td>{cells}</tr>"
    head = "".join(f"<th class='n'>{_e(p)}</th>" for p in provs)
    beh = {p: pipe[p].get("behaviour") for p in provs if pipe[p].get("behaviour")}
    beh_html = ""
    if beh:
        brow = [("Cases scored", "scored_cases", str), ("Cases passed", "behaviour_pass_rate", _pct),
                ("Adversarial cases", "adversarial_cases", str),
                ("Adversarial cases sent to a human", "adversarial_escalation_rate", _pct),
                ("Flagged as prompt injection", "case_injection_hits", str), ("PII cases masked", "pii_cases_masked", str)]
        bbody = "".join(f"<tr><td>{n}</td>" + "".join(
            f"<td class='n'>{f(beh[p][k]) if p in beh and beh[p].get(k) is not None else '–'}</td>" for p in provs)
            + "</tr>" for n, k, f in brow)
        beh_html = (f"<h3>Hand-written routine and adversarial cases</h3><div class='tablewrap'><table><thead><tr>"
                    f"<th>Behaviour</th>{head}</tr></thead><tbody>{bbody}</tbody></table></div>")
    return f"""
<div class="split"><div class="facts"><div class="tablewrap"><table><thead><tr><th>Writer</th>{head}</tr></thead>
<tbody>{body}</tbody></table></div></div>
<div class="facts"><div class="panel"><h3>Where tickets went</h3>
{_legend([("s1", "Auto-draft"), ("s2", "Agent review"), ("s3", "Page on-call")])}{_svg_tiers(pipe)}</div>{beh_html}</div></div>"""


def _section_leakage(rep: dict) -> str:
    leak = rep.get("leakage")
    if not leak:
        return _missing("leakage check", "make sentinel-eval")
    checks = [
        (leak.get("holdout_ids_in_index") == 0, f"{leak.get('holdout_ids_in_index')} holdout tickets in the search index"),
        (leak.get("indexed_not_in_kb") == 0, f"{leak.get('indexed_not_in_kb')} indexed tickets from outside the knowledge base"),
        (leak.get("ticket_id_overlap") == 0, f"{leak.get('ticket_id_overlap')} ticket ids shared between the two splits"),
        (bool(leak.get("kb_has_answers")), "Knowledge-base tickets carry their resolved answers; holdout answers are never indexed"),
    ]
    items = "".join(f"<li>{_pill(ok, 'Pass', 'Check')}<span>{_e(text)}</span></li>" for ok, text in checks)
    dup = leak.get("identical_body_overlap")
    extra = (f"<p class='note'>{dup} holdout ticket has the same body text as a knowledge-base ticket "
             "(a duplicate in the source data). It is reported, not removed.</p>") if dup else ""
    return f"<ul class='checks'>{items}</ul>{extra}"


def _sources(inputs: dict, paths: dict[str, Path]) -> str:
    rows = ""
    for key, label in (("report", "Holdout eval"), ("thresholds", "Tuned thresholds"), ("dial", "Safety dial"),
                       ("calibration", "Calibration")):
        d = inputs.get(key)
        when = (d or {}).get("generated_at", "–") if d else "missing"
        rows += f"<tr><td>{label}</td><td><code>{_e(paths[key])}</code></td><td>{_e(when)}</td></tr>"
    return (f"<div class='tablewrap'><table class='small'><thead><tr><th>Result</th><th>File</th><th>Generated</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>")


REPORT_CSS = """
:root{
  /* Layout: one 1080px reading column; each section pairs a chart panel with its numbers, stacking on phones. */
  --bg:#0a0e16;--surface:#0f131c;--surface-2:#141822;--line:#1e2330;
  --ink:#e8ebf3;--ink-2:#a7afc2;--ink-3:#737c93;--accent:#818cf8;
  --s1:#3987e5;--s2:#d95926;--s3:#199e70;--good:#0ca30c;--warn:#fab219;--crit:#d03b3b;
  --display:"Space Grotesk",ui-sans-serif,system-ui,sans-serif;
  --body:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  color-scheme:dark;
}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){
  --bg:#f5f6fa;--surface:#ffffff;--surface-2:#eef0f6;--line:#dde1ea;--ink:#0e1220;--ink-2:#465068;--ink-3:#687088;
  --accent:#4f46e5;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;color-scheme:light}}
:root[data-theme="light"]{--bg:#f5f6fa;--surface:#ffffff;--surface-2:#eef0f6;--line:#dde1ea;--ink:#0e1220;
  --ink-2:#465068;--ink-3:#687088;--accent:#4f46e5;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--body);-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding-block:44px 72px;padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:56px}
header{display:grid;gap:12px}
.eyebrow{font:600 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1,h2,h3{font-family:var(--display);font-weight:600;text-wrap:balance;margin:0;line-height:1.2}
h1{font-size:clamp(28px,4.2vw,40px)}
h2{font-size:22px}
h3{font-size:15px;color:var(--ink-2);font-weight:500}
.lede,.sub{color:var(--ink-2);max-width:68ch;margin:0}
.meta{color:var(--ink-3);font:12.5px var(--mono)}
code{font:0.9em var(--mono);background:var(--surface-2);border:1px solid var(--line);border-radius:4px;padding:1px 5px}
.notes{display:grid;gap:8px;margin:0;padding:0;list-style:none}
.notes li{display:flex;gap:10px;align-items:flex-start;background:var(--surface-2);border:1px solid var(--line);
  border-radius:10px;padding:10px 14px;color:var(--ink-2);font-size:14px}
.notes li::before{content:"!";flex:none;width:20px;height:20px;border-radius:50%;background:var(--warn);color:#1a1300;
  font:700 12px/20px var(--mono);text-align:center;margin-top:1px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 18px 16px;display:grid;gap:4px;align-content:start}
.tile .k{color:var(--ink-2);font-size:13px}
.tile .v{font:600 36px/1.1 var(--display);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.tile .s{color:var(--ink-3);font-size:12.5px}
section{display:grid;gap:16px}
section>header{gap:6px}
.split{display:grid;gap:20px;grid-template-columns:1fr}
@media (min-width:880px){.split{grid-template-columns:minmax(0,3fr) minmax(0,2fr)}}
.split>*,.facts{min-width:0}
.facts{display:grid;gap:16px;align-content:start}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;display:grid;gap:10px;min-width:0}
svg{width:100%;height:auto;display:block;overflow:visible}
svg.tiers{max-width:440px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:2px;display:inline-block}
.sw.s1{background:var(--s1)}.sw.s2{background:var(--s2)}.sw.s3{background:var(--s3)}
.grid{stroke:var(--line);stroke-width:1}
.target{stroke:var(--ink-3);stroke-width:1.25;stroke-dasharray:4 4}
.ax{fill:var(--ink-3);font:11px var(--mono)}
.lb{fill:var(--ink-2);font:12.5px var(--body)}
.lbs{fill:var(--ink);font:600 12.5px var(--body)}
.vl{fill:var(--ink);font:600 11.5px var(--mono)}
path.s1,rect.s1,circle.s1{fill:var(--s1)} path.s2,rect.s2,circle.s2{fill:var(--s2)} rect.s3{fill:var(--s3)}
.s1l,.s2l{fill:none;stroke-width:2;stroke-linejoin:round}
.s1l{stroke:var(--s1)} .s2l{stroke:var(--s2)}
.ring{stroke:var(--surface);stroke-width:2}
.halo{fill:none;stroke:var(--ink);stroke-width:1.25}
.hit{fill:transparent;cursor:default}
.multiples{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
figure{margin:0;display:grid;gap:6px;min-width:0}
figcaption{font:600 14px var(--display)}
figcaption span{font:12px var(--mono);color:var(--ink-3);margin-left:6px;font-weight:400}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--ink-3);font:600 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;
  padding:0 10px 8px 0;border-bottom:1px solid var(--line);vertical-align:bottom}
td{padding:8px 10px 8px 0;border-bottom:1px solid var(--line);color:var(--ink-2)}
td:first-child{color:var(--ink)}
.n{text-align:right;white-space:nowrap}
.strong{color:var(--ink);font-weight:600}
table.small td{font-size:12.5px}
dl{margin:0;display:grid;gap:0}
dl div{display:flex;justify-content:space-between;gap:16px;padding:8px 0;border-bottom:1px solid var(--line)}
dt{color:var(--ink-2);font-size:13.5px} dd{margin:0;font:600 13.5px var(--body);font-variant-numeric:tabular-nums}
.note,.missing{color:var(--ink-3);font-size:13px;margin:0;max-width:68ch}
.missing{background:var(--surface-2);border:1px dashed var(--line);border-radius:10px;padding:14px}
.checks{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.checks li{display:flex;gap:12px;align-items:center;color:var(--ink-2)}
.pill{display:inline-flex;align-items:center;gap:6px;flex:none;font:600 12px var(--body);padding:2px 9px 2px 3px;
  border:1px solid var(--line);border-radius:999px;color:var(--ink)}
.pill i{font-style:normal;width:16px;height:16px;border-radius:50%;display:inline-grid;place-items:center;font-size:10px;color:#fff}
.pill.ok i{background:var(--good)} .pill.bad i{background:var(--crit)}
ol.method{margin:0;padding-left:20px;display:grid;gap:8px;color:var(--ink-2);max-width:72ch}
ol.method b{color:var(--ink);font-weight:600}
#tip{position:fixed;z-index:20;pointer-events:none;max-width:280px;background:var(--ink);color:var(--bg);
  font:12px/1.4 var(--body);padding:6px 9px;border-radius:6px}
footer{display:grid;gap:10px;color:var(--ink-3);font-size:13px}
"""

REPORT_JS = """
(function(){var tip=document.getElementById('tip');
function place(e){var p=14,r=tip.getBoundingClientRect(),x=e.clientX+p,y=e.clientY+p;
if(x+r.width>innerWidth-8)x=e.clientX-r.width-p;if(y+r.height>innerHeight-8)y=e.clientY-r.height-p;
tip.style.left=x+'px';tip.style.top=y+'px';}
document.addEventListener('pointermove',function(e){var t=e.target.closest&&e.target.closest('[data-tip]');
if(!t){tip.hidden=true;return;}tip.textContent=t.getAttribute('data-tip');tip.hidden=false;place(e);});
document.addEventListener('pointerleave',function(){tip.hidden=true;});})();
"""


def render_html(inputs: dict[str, dict | None], paths: dict[str, Path] | None = None) -> str:
    """The whole page as one string. Pure: reads nothing, so tests can feed it small dicts."""
    paths = paths or {"report": LATEST_DIR / "report.json", "thresholds": THRESHOLDS_JSON, "dial": DIAL_JSON,
                      "calibration": CALIBRATION_JSON}
    rep = inputs.get("report") or {}
    notes = staleness_notes(inputs)
    notes_html = ("<ul class='notes'>" + "".join(f"<li><span>{n}</span></li>" for n in notes) + "</ul>") if notes else ""
    holdout = (rep.get("triage") or {}).get("holdout_tickets")
    kb = (rep.get("leakage") or {}).get("kb_tickets")
    val_tickets = ((inputs.get("thresholds") or {}).get("validation") or {}).get("tickets")
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>SentinelDesk Eval Report</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@500;600&display=swap">
<style>{REPORT_CSS}</style></head>
<body><div id="tip" hidden></div><main class="wrap">
<header><div class="eyebrow">SentinelDesk · evaluation</div>
<h1>How well SentinelDesk triages, escalates and drafts</h1>
<p class="lede">Every number below comes from tickets the model never trained on. Hover a chart for exact values.</p>
<div class="meta">Page built {built} from the saved eval outputs · regenerate with <code>python -m eval.sentinel_eval --html-only</code></div>
{notes_html}</header>
{_section_tiles(inputs)}
<section><header><h2>Triage on unseen tickets</h2>
<p class="sub">The classifier labels type, priority and team from the raw subject and body. Scored on the full holdout{f" of {holdout:,} tickets" if holdout else ""}; Macro-F1 weighs every class equally, so rare classes count.</p></header>
{_section_triage(rep)}</section>
<section><header><h2>Safety gate: catching urgent incidents</h2>
<p class="sub">Each dot is one gate setting tried on the validation slice. Higher catches more high-priority incidents; further right pages on-call more often. We kept the setting with the fewest pages that still catches 90%. The holdout was not used to choose it.</p></header>
{_section_dial(inputs.get("dial"), inputs.get("thresholds"))}</section>
<section><header><h2>Confidence you can act on</h2>
<p class="sub">When the model says 80% sure, it should be right about 80% of the time: points on the dashed diagonal. Temperature scaling pulls each head onto it. ECE is the average gap; lower is better.</p></header>
{_section_calibration(inputs.get("calibration"))}</section>
<section><header><h2>Drafted replies, end to end</h2>
<p class="sub">Unseen holdout tickets run through the whole pipeline: triage, safety gate, retrieval of past resolved tickets, and a draft whose every citation is checked against the ticket it quotes.</p></header>
{_section_pipeline(rep)}</section>
<section><header><h2>No leakage between training and test</h2>
<p class="sub">The search index holds only knowledge-base tickets, so a draft can never quote the answer to the ticket being scored.</p></header>
{_section_leakage(rep)}</section>
<section><header><h2>How we tested</h2></header>
<ol class="method">
<li><b>Split once, 80/20.</b> {f"{kb:,}" if kb else "The"} knowledge-base tickets train the classifier and fill the search index; {f"{holdout:,}" if holdout else "the"} holdout tickets are set aside.</li>
<li><b>Tune on validation only.</b> Gate thresholds and calibration are fit on a validation slice of the knowledge base{f" ({val_tickets:,} tickets)" if val_tickets else ""}.</li>
<li><b>Score the holdout once.</b> Holdout labels are read only to score predictions made from raw text.</li>
</ol></section>
<footer><h3>Sources</h3>{_sources(inputs, paths)}</footer>
</main><script>{REPORT_JS}</script></body></html>
"""


def write_html_report(out: Path = HTML_OUT, inputs: dict[str, dict | None] | None = None) -> Path:
    """Render the eval page from the saved outputs and write it to docs/demo/eval_report.html."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(inputs if inputs is not None else load_report_inputs()), encoding="utf-8")
    return out


def _refresh_html() -> None:
    try:
        print(f"    eval page: {write_html_report()}")
    except Exception as e:  # noqa: BLE001 - the page is a convenience; never fail an eval run over it
        print(f"    eval page not written: {e}")


def main(argv: Iterable[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="Evaluate SentinelDesk on the holdout split.")
    ap.add_argument("--sample", type=int, default=120, help="holdout tickets through the full pipeline")
    ap.add_argument("--compare", nargs="*", default=None, help="providers to compare, e.g. gemini extractive")
    ap.add_argument("--triage-only", action="store_true", help="classifier metrics only (no LLM)")
    ap.add_argument("--skip-cases", action="store_true")
    ap.add_argument("--html-only", action="store_true",
                    help=f"only rebuild {HTML_OUT} from the saved outputs (seconds, no model)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.html_only:
        inputs = load_report_inputs()
        path = write_html_report(inputs=inputs)
        print(f"written {path}")
        return {"html": str(path), "inputs": {k: v is not None for k, v in inputs.items()}}

    from sentinel.pipeline import SentinelAgent
    from sentinel.triage import TriageModel, evaluate as evaluate_triage

    out_dir = OUT_ROOT / f"sentinel-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    kb, test = dataset.load_split()
    report: dict[str, object] = {"generated_at": datetime.now().isoformat(timespec="seconds"), "run_dir": str(out_dir)}

    print("1/3 triage on the full holdout")
    model = TriageModel.load()
    triage_metrics = evaluate_triage(model, test, verbose=False)
    report["triage"] = triage_metrics
    for k, v in triage_metrics.items():
        print(f"    {k:<42} {v}")
    report["calibration"] = calibration_section(model, test)
    print(f"    calibration: {'available' if report['calibration']['available'] else report['calibration']['reason']}")

    if args.triage_only:
        latest = write_report(out_dir, report)
        print(f"\nwritten to {out_dir} and {latest}")
        _refresh_html()
        return report

    agent = SentinelAgent(triage_model=model)
    report["leakage"] = verify_no_leakage(kb, test, agent)
    print(f"\n    leakage check: {report['leakage']}")
    assert report["leakage"]["ok"], "LEAKAGE: the index contains tickets outside kb_train"
    agent.warm_up()
    try:
        from sentinel import thresholds

        report["thresholds"] = thresholds.load(agent.settings)
    except Exception as e:  # noqa: BLE001
        report["thresholds"] = {"error": str(e)[:200]}

    providers = args.compare or [agent.settings.llm_provider]
    per_provider: dict[str, dict] = {}
    for provider in providers:
        print(f"\n2/3 end-to-end on {args.sample} unseen holdout tickets [{provider}]")
        t0 = time.perf_counter()
        summary, df = run_pipeline_sample(agent, test, args.sample, provider)
        summary["wall_clock_s"] = round(time.perf_counter() - t0, 1)
        per_provider[provider] = summary
        df.to_csv(out_dir / f"pipeline-{provider}.csv", index=False, encoding="utf-8")
        for k, v in summary.items():
            print(f"    {k:<42} {v}")

        if not args.skip_cases:
            print(f"\n3/3 behaviour cases [{provider}]")
            case_summary, case_df = run_behaviour_cases(agent, provider)
            case_df.to_csv(out_dir / f"cases-{provider}.csv", index=False, encoding="utf-8")
            summary["behaviour"] = case_summary
            for k, v in case_summary.items():
                print(f"    {k:<42} {v}")
            for _, m in case_df[case_df["correct"] == False].iterrows():  # noqa: E712
                print(f"    MISS {m['id']}: failed {m['failed_checks']} (tier {m['tier']}; {m['reasons'][:120]})")

    report["pipeline"] = per_provider
    latest = write_report(out_dir, report)
    path = chart(out_dir, triage_metrics, per_provider)
    if path:
        shutil.copyfile(path, LATEST_DIR / "chart.png")
    print(f"\nwritten to {out_dir} and {latest}" + (f" (+ {path.name})" if path else ""))
    _refresh_html()
    return report


if __name__ == "__main__":
    main()
