"""Benchmark the agent on a JSONL case file and write metrics + a chart for the pitch deck.

Usage:
    python -m eval.run                                   # eval/cases.jsonl, default provider
    python -m eval.run --provider ollama --cases my.jsonl
    python -m eval.run --compare extractive ollama       # one row per provider in summary

Outputs to data/eval/<timestamp>/:
    records.jsonl   full AgentAnswer per case
    results.csv     one row per case (also easy to upload into an external eval tool)
    summary.json    aggregate metrics per provider
    chart.png       metrics bar chart + latency (needs: pip install -e ".[plots]")

Metrics (answerable = cases with should_abstain false):
    pass_rate             correct abstain, or an answer citing an expected source AND (if the case lists
                          expected_quote_contains) whose verified quote contains the expected text
    abstain_accuracy      should_abstain matches whether the agent abstained
    recall_at_k           answerable cases where an expected source was RETRIEVED (before any LLM):
                          measures the embedder/index, independent of the model
    source_hit_rate       answerable cases where a finding cites an expected source
    content_hit_rate      answerable cases with expected_quote_contains where a verified quote matches
    source_precision      share of findings citing an expected source (answerable cases, mean)
    Grounding, as a share of all findings the model drafted:
    fabrication_rate      cited an unknown chunk or a quote not in it (made-up evidence)
    claim_mismatch_rate   real quote, but the claim says something else (number, negation, topic)
    low_confidence_rate   the model's own confidence was below MIN_CONFIDENCE (not a hallucination)
    rejection_rate        all of the above
    latency_p50/p95_ms
"""

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

from agent.pipeline import Agent
from shared.contracts import AgentAnswer, EvalCase, EvalRecord


def load_cases(path: Path) -> list[EvalCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EvalCase.model_validate_json(l) for l in lines if l.strip() and not l.lstrip().startswith("//")]


def score(case: EvalCase, answer: AgentAnswer) -> EvalRecord:
    def matches(source: str) -> bool:
        return any(exp in source for exp in case.expected_sources)

    abstain_correct = answer.abstained == case.should_abstain
    hits = [f for f in answer.findings if matches(f.evidence_source)]
    source_hit = bool(hits)
    precision = len(hits) / len(answer.findings) if answer.findings and case.expected_sources else None
    retrieval_hit = any(matches(r.chunk.source) for r in answer.retrieved) if case.expected_sources else None
    content_hit = None
    if case.expected_quote_contains:
        wanted = [w.lower() for w in case.expected_quote_contains]
        content_hit = any(w in f.evidence_quote.lower() for f in answer.findings for w in wanted)
    if case.should_abstain:
        passed = answer.abstained
    else:
        passed = (not answer.abstained and (source_hit or not case.expected_sources)
                  and content_hit is not False)
    return EvalRecord(
        case=case,
        answer=answer,
        abstain_correct=abstain_correct,
        retrieval_hit=retrieval_hit,
        source_hit=source_hit,
        content_hit=content_hit,
        source_precision=precision,
        passed=passed,
    )


def _rate(flags: list[bool | None]) -> float | None:
    vals = [f for f in flags if f is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 1)


def summarize(records: list[EvalRecord]) -> dict:
    answerable = [r for r in records if not r.case.should_abstain]
    precisions = [r.source_precision for r in answerable if r.source_precision is not None]
    raw = sum(len(r.answer.findings) + len(r.answer.rejected) for r in records)
    kinds = [rej.kind for r in records for rej in r.answer.rejected]

    def share(*wanted: str) -> float:
        return round(sum(k in wanted for k in kinds) / raw, 3) if raw else 0.0

    latencies = [r.answer.latency_ms for r in records]
    first = records[0].answer if records else None
    return {
        "provider": first.provider if first else None,
        "model": first.model if first else None,
        "n_cases": len(records),
        "top_k": max((len(r.answer.retrieved) for r in records), default=0),
        "pass_rate": round(sum(r.passed for r in records) / len(records), 3) if records else 0,
        "abstain_accuracy": round(sum(r.abstain_correct for r in records) / len(records), 3) if records else 0,
        "recall_at_k": _rate([r.retrieval_hit for r in answerable]),
        "source_hit_rate": _rate([r.source_hit for r in answerable]),
        "content_hit_rate": _rate([r.content_hit for r in answerable]),
        "source_precision": round(statistics.mean(precisions), 3) if precisions else None,
        "fabrication_rate": share("unknown_chunk", "quote_not_found", "quote_too_short"),
        "claim_mismatch_rate": share("claim_mismatch"),
        "low_confidence_rate": share("low_confidence", "bad_confidence"),
        "rejection_rate": round(len(kinds) / raw, 3) if raw else 0.0,
        "errors": sum(1 for r in records if r.answer.error),
        "fallbacks": sum(1 for r in records if r.answer.fell_back),
        "latency_p50_ms": _pct(latencies, 0.5),
        "latency_p95_ms": _pct(latencies, 0.95),
    }


def write_outputs(out: Path, records_by_provider: dict[str, list[EvalRecord]], summaries: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "records.jsonl").open("w", encoding="utf-8") as f:
        for recs in records_by_provider.values():
            for r in recs:
                f.write(r.model_dump_json() + "\n")
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["provider", "case_id", "question", "passed", "abstained", "should_abstain", "retrieval_hit",
                    "content_hit", "n_findings", "n_rejected", "rejection_kinds", "top_source", "top_locator",
                    "top_claim", "confidence", "latency_ms", "error"])
        for provider, recs in records_by_provider.items():
            for r in recs:
                a, top = r.answer, (r.answer.findings[0] if r.answer.findings else None)
                w.writerow([provider, r.case.id, r.case.question, r.passed, a.abstained, r.case.should_abstain,
                            r.retrieval_hit, r.content_hit, len(a.findings), len(a.rejected),
                            ",".join(x.kind for x in a.rejected), top.evidence_source if top else "",
                            top.line_or_timestamp if top else "", top.claim if top else "",
                            top.confidence_score if top else "", a.latency_ms, a.error or ""])
    (out / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    _chart(out / "chart.png", summaries)


def _chart(path: Path, summaries: list[dict]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print('(skipping chart: pip install -e ".[plots]")')
        return
    metrics = ["pass_rate", "recall_at_k", "content_hit_rate", "abstain_accuracy",
               "fabrication_rate", "claim_mismatch_rate"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [3, 1]})
    width = 0.8 / max(1, len(summaries))
    for i, s in enumerate(summaries):
        xs = [m + i * width for m in range(len(metrics))]
        ax1.bar(xs, [s.get(m) or 0 for m in metrics], width, label=f"{s['provider']} ({s['model']})")
        ax2.bar(i, s["latency_p50_ms"], 0.6, label=s["provider"])
    ax1.set_xticks([m + width * (len(summaries) - 1) / 2 for m in range(len(metrics))])
    ax1.set_xticklabels([m.replace("_", " ") for m in metrics])
    ax1.set_ylim(0, 1)
    ax1.set_title(f"Quality, {summaries[0]['n_cases']} cases, top_k={summaries[0]['top_k']} "
                  "(fabrication / claim mismatch: lower is better)", fontsize=9)
    ax1.legend(fontsize=8)
    ax2.set_xticks(range(len(summaries)))
    ax2.set_xticklabels([s["provider"] for s in summaries])
    ax2.set_title("Latency p50 (ms)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    print(f"chart: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval harness.")
    parser.add_argument("--cases", type=Path, default=Path(__file__).parent / "cases.jsonl")
    parser.add_argument("--provider", default=None, help="extractive | ollama | gemini (default from .env)")
    parser.add_argument("--compare", nargs="+", default=None, help="run several providers back to back")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--fallback", action="store_true",
                        help="allow the fallback chain (off by default so each provider is measured on its own)")
    parser.add_argument("--no-warm-up", action="store_true",
                        help="skip loading models first (measures cold-start latency on case 1)")
    args = parser.parse_args()

    agent = Agent()
    cases = load_cases(args.cases)
    providers = args.compare or [args.provider or agent.settings.llm_provider]
    out = args.out or Path("data/eval") / time.strftime("%Y%m%d-%H%M%S")

    if agent.store.count() == 0:
        print("warning: the memory index is empty; run an ingest_* script first (e.g. `make index-samples`)")

    # Load models first so case 1 isn't charged the cold start (or its load-time 500).
    if agent.settings.warm_up and not args.no_warm_up:
        t = time.perf_counter()
        status = agent.warm_up(providers)
        if status:
            print(f"warm-up ({(time.perf_counter() - t):.1f} s): {status}")

    records_by_provider, summaries = {}, []
    for provider in providers:
        recs = []
        for case in cases:
            r = score(case, agent.ask(case.question, provider=provider, fallback=args.fallback))
            recs.append(r)
            mark = "PASS" if r.passed else "FAIL"
            print(f"[{provider}] {mark} {case.id:28s} {r.answer.latency_ms:8.1f} ms  {r.answer.error or ''}")
        records_by_provider[provider] = recs
        summaries.append(summarize(recs))

    write_outputs(out, records_by_provider, summaries)
    print(json.dumps(summaries, indent=2))
    print(f"outputs: {out}")


if __name__ == "__main__":
    main()
