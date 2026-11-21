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

    python -m eval.sentinel_eval                          # 120 holdout tickets, default provider
    python -m eval.sentinel_eval --sample 20 --compare extractive
    python -m eval.sentinel_eval --compare gemini extractive
    python -m eval.sentinel_eval --triage-only            # seconds, no LLM
"""

from __future__ import annotations

import argparse
import importlib
import json
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


def main(argv: Iterable[str] | None = None) -> dict:
    from sentinel.pipeline import SentinelAgent
    from sentinel.triage import TriageModel, evaluate as evaluate_triage

    ap = argparse.ArgumentParser(description="Evaluate SentinelDesk on the holdout split.")
    ap.add_argument("--sample", type=int, default=120, help="holdout tickets through the full pipeline")
    ap.add_argument("--compare", nargs="*", default=None, help="providers to compare, e.g. gemini extractive")
    ap.add_argument("--triage-only", action="store_true", help="classifier metrics only (no LLM)")
    ap.add_argument("--skip-cases", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

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
    return report


if __name__ == "__main__":
    main()
