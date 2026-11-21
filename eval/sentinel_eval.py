"""SentinelDesk holdout evaluation.

Three things are measured, in this order, because they answer three different judge questions:

  1. Triage      - the full 5,718-ticket holdout, Macro-F1 per head + High-Priority Incident Recall.
                   Labels are read only to score predictions that were made from raw text.
  2. End to end  - a sample of unseen holdout tickets through the whole pipeline: groundedness,
                   citation rejection rate, escalation rate, language match, p50/p95 latency.
  3. Behaviour   - hand-written adversarial and routine cases (eval/sentinel_cases.jsonl): does the
                   gate escalate refund/legal/credential demands and prompt injection?

Everything is written to data/eval/sentinel-<timestamp>/ as JSON + CSV (+ chart.png with matplotlib).

    python -m eval.sentinel_eval                          # 120 holdout tickets, default provider
    python -m eval.sentinel_eval --sample 200
    python -m eval.sentinel_eval --compare ollama extractive
    python -m eval.sentinel_eval --triage-only            # seconds, no LLM
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from sentinel import dataset
from sentinel.pipeline import SentinelAgent
from sentinel.triage import TriageModel, evaluate as evaluate_triage

OUT_ROOT = Path("data/eval")
CASES = Path("eval/sentinel_cases.jsonl")


def verify_no_leakage(kb: pd.DataFrame, test: pd.DataFrame, agent: SentinelAgent) -> dict[str, object]:
    """Judge-facing proof: no holdout ticket id is in the index, and the index only holds kb ids."""
    report = dict(dataset.leakage_report(kb, test))
    kb_ids = set(kb["ticket_id"])
    indexed = set(agent.store.sources())
    report["indexed_chunks"] = len(indexed)
    report["indexed_not_in_kb"] = len(indexed - kb_ids)
    report["holdout_ids_in_index"] = len(indexed & set(test["ticket_id"]))
    report["ok"] = bool(report["ok"]) and report["indexed_not_in_kb"] == 0 and report["holdout_ids_in_index"] == 0
    return report


def run_pipeline_sample(
    agent: SentinelAgent, test: pd.DataFrame, n: int, provider: str | None, seed: int = 7
) -> tuple[dict[str, object], pd.DataFrame]:
    sample = test.sample(n=min(n, len(test)), random_state=seed).reset_index(drop=True)
    rows = []
    for i, row in enumerate(sample.to_dict("records"), start=1):
        result = agent.triage(row.get("subject") or None, row["body"], provider=provider)
        top = result.precedents[0] if result.precedents else None
        rows.append(
            {
                "ticket_id": row["ticket_id"],
                "gold_type": row["type"], "pred_type": result.triage.type,
                "gold_queue": row["queue"], "pred_queue": result.triage.queue,
                "gold_priority": row["priority"], "pred_priority": result.triage.priority,
                "gold_language": row["language"], "detected_language": result.detected_language,
                "triage_confidence": result.triage.triage_confidence,
                "escalation": result.escalation,
                "escalation_reasons": " ; ".join(result.escalation_reasons),
                "grounded": result.grounded,
                "refused": result.refused,
                "n_verified": len(result.verified_citations),
                "n_rejected": len(result.rejected_citations),
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
    drafted = df[df["reply_chars"] > 0]
    latencies = sorted(df["latency_ms"])
    summary = {
        "tickets": len(df),
        "provider": provider or agent.settings.llm_provider,
        "groundedness_rate": round(float(df["grounded"].mean()), 4),
        "grounded_of_drafted": round(float(drafted["grounded"].mean()), 4) if len(drafted) else 0.0,
        "refusal_rate": round(float(df["refused"].mean()), 4),
        "escalation_rate": round(float((df["escalation"] == "ESCALATE").mean()), 4),
        "auto_draft_rate": round(float((df["escalation"] == "AUTO_DRAFT").mean()), 4),
        "citations_verified_total": int(df["n_verified"].sum()),
        "citations_rejected_total": int(df["n_rejected"].sum()),
        "citation_rejection_rate": round(
            float(df["n_rejected"].sum()) / max(int(df["n_verified"].sum() + df["n_rejected"].sum()), 1), 4),
        "language_match_rate": round(float((df["detected_language"] == df["gold_language"]).mean()), 4),
        "retrieved_queue_match_rate": round(float((df["top_precedent_queue"] == df["gold_queue"]).mean()), 4),
        "mean_top_similarity": round(float(df["top_similarity"].mean()), 4),
        "latency_p50_ms": round(statistics.median(latencies), 1),
        "latency_p95_ms": round(latencies[int(len(latencies) * 0.95) - 1], 1) if latencies else 0.0,
        "latency_mean_ms": round(float(df["latency_ms"].mean()), 1),
        "errors": int((df["error"] != "").sum()),
    }
    return summary, df


def run_behaviour_cases(agent: SentinelAgent, provider: str | None) -> tuple[dict[str, object], pd.DataFrame]:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for c in cases:
        result = agent.triage(c.get("subject") or None, c["body"], provider=provider)
        expected = c.get("expect_escalation")
        escalated = result.escalation == "ESCALATE"
        rows.append(
            {
                "id": c["id"],
                "expect_escalation": expected,
                "escalated": escalated,
                "correct": None if expected is None else bool(escalated) == bool(expected),
                "reasons": " ; ".join(result.escalation_reasons),
                "grounded": result.grounded,
                "refused": result.refused,
                "language": result.detected_language,
                "pii_masked": result.pii_masked,
                "pii_found": json.dumps(result.pii_found),
                "latency_ms": result.latency_ms,
                "reply": (result.draft_reply or "")[:400],
            }
        )
    df = pd.DataFrame(rows)
    scored = df[df["expect_escalation"].notna()]
    summary = {
        "cases": len(df),
        "adversarial_cases": len(scored),
        "adversarial_escalation_rate": round(float(scored["correct"].mean()), 4) if len(scored) else 0.0,
        "pii_cases_masked": int(df["pii_masked"].sum()),
    }
    return summary, df


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate SentinelDesk on the holdout split.")
    ap.add_argument("--sample", type=int, default=120, help="holdout tickets through the full pipeline")
    ap.add_argument("--compare", nargs="*", default=None, help="providers to compare, e.g. ollama extractive")
    ap.add_argument("--triage-only", action="store_true", help="classifier metrics only (no LLM)")
    ap.add_argument("--skip-cases", action="store_true")
    args = ap.parse_args()

    out_dir = OUT_ROOT / f"sentinel-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    kb, test = dataset.load_split()
    report: dict[str, object] = {"generated_at": datetime.now().isoformat(timespec="seconds")}

    print("1/3 triage on the full holdout")
    model = TriageModel.load()
    triage_metrics = evaluate_triage(model, test, verbose=False)
    report["triage"] = triage_metrics
    for k, v in triage_metrics.items():
        print(f"    {k:<42} {v}")

    if args.triage_only:
        (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwritten to {out_dir}")
        return

    agent = SentinelAgent()
    report["leakage"] = verify_no_leakage(kb, test, agent)
    print(f"\n    leakage check: {report['leakage']}")
    assert report["leakage"]["ok"], "LEAKAGE: the index contains tickets outside kb_train"
    agent.warm_up()

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
            summary.update(case_summary)
            for k, v in case_summary.items():
                print(f"    {k:<42} {v}")
            missed = case_df[(case_df["correct"] == False)]  # noqa: E712
            for _, m in missed.iterrows():
                print(f"    MISS {m['id']}: expected escalation, got {m['escalated']}")

    report["pipeline"] = per_provider
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    path = chart(out_dir, triage_metrics, per_provider)
    print(f"\nwritten to {out_dir}" + (f" (+ {path.name})" if path else ""))


if __name__ == "__main__":
    main()
