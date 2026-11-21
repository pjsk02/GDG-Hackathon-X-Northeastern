"""Offline tests for the eval report page in eval/sentinel_eval.py (owner A). Small dicts, no data/ files."""

from __future__ import annotations

import json
from pathlib import Path

from eval import sentinel_eval as se

THR = {"triage_confidence_min": 0.55, "high_priority_alert_probability": 0.27, "retrieval_similarity_min": 0.86}


def _bins(acc: float) -> list[dict]:
    return [{"lower": 0.5, "upper": 0.6, "count": 10, "mean_confidence": 0.55, "accuracy": acc},
            {"lower": 0.9, "upper": 1.0, "count": 0, "mean_confidence": 0.0, "accuracy": 0.0}]


def _inputs(report_thresholds: dict | None = None, provider: str = "gemini") -> dict:
    report = {
        "generated_at": "2026-11-21T14:27:00",
        "triage": {"holdout_tickets": 5718, "type_macro_f1": 0.868, "type_accuracy": 0.855,
                   "priority_macro_f1": 0.609, "priority_accuracy": 0.629, "queue_macro_f1": 0.567,
                   "queue_accuracy": 0.558, "language_accuracy": 0.905, "high_priority_incident_count": 995,
                   "high_priority_incident_recall": 0.654, "high_priority_incident_recall_via_gate": 0.745,
                   "latency_ms_per_ticket": 0.36},
        "leakage": {"kb_tickets": 22869, "holdout_ids_in_index": 0, "indexed_not_in_kb": 0, "ticket_id_overlap": 0,
                    "identical_body_overlap": 1, "kb_has_answers": True, "indexed_chunks": 22869},
        "thresholds": report_thresholds if report_thresholds is not None else dict(THR),
        "pipeline": {provider: {"tickets": 120, "groundedness_rate": 0.992, "citations_verified_total": 241,
                                "citations_rejected_total": 0, "injection_hits": 0, "tier_auto_draft_rate": 0.25,
                                "tier_agent_review_rate": 0.12, "tier_oncall_rate": 0.63, "latency_p50_ms": 1340,
                                "latency_p95_ms": 6588, "errors": 0,
                                "behaviour": {"scored_cases": 21, "behaviour_pass_rate": 1.0}}},
    }
    thresholds = {**THR, "generated_at": "2026-11-21T19:20:08+00:00", "target_met": True,
                  "validation": {"hpi_recall": 0.901, "oncall_rate": 0.597, "tickets": 2287},
                  "baseline_defaults": {"triage_confidence_min": 0.55, "high_priority_alert_probability": 0.5,
                                        "retrieval_similarity_min": 0.55, "hpi_recall": 0.746, "oncall_rate": 0.353}}
    dial = {"points": [{**THR, "hpi_recall": r, "oncall_rate": o} for r, o in ((0.71, 0.25), (0.8, 0.45), (0.95, 0.8))],
            "chosen": {**THR, "hpi_recall": 0.901, "oncall_rate": 0.597}}
    calibration = {"tickets": 5718, "split": "holdout",
                   "heads": {"type": {"uncalibrated": {"ece": 0.013, "bins": _bins(0.6)},
                                      "calibrated": {"ece": 0.010, "accuracy": 0.855, "bins": _bins(0.56)}}}}
    return {"report": report, "dial": dial, "calibration": calibration, "thresholds": thresholds}


def test_render_html_shows_every_section_and_headline_numbers():
    page = se.render_html(_inputs())
    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</html>")
    assert "<title>SentinelDesk Eval Report</title>" in page
    for heading in ("Triage on unseen tickets", "Safety gate", "Confidence you can act on",
                    "Drafted replies", "No leakage", "How we tested"):
        assert heading in page
    for number in ("90.1%", "0.868", "99%", "5,718", "Tuned gate", "Old defaults", "ECE 0.013 → 0.010"):
        assert number in page
    assert page.count("<svg") == 4  # triage bars, safety dial, one reliability diagram, tier split
    assert "class='missing'" not in page and 'class="missing"' not in page


def test_empty_calibration_bins_are_not_plotted():
    svg = se._svg_reliability("Type", _inputs()["calibration"]["heads"]["type"])
    assert svg.count('class="hit"') == 2  # one non-empty bin per variant


def test_missing_outputs_say_how_to_produce_them():
    page = se.render_html({"report": None, "dial": None, "calibration": None, "thresholds": None})
    assert "make tune &amp;&amp; make dial" in page
    assert "make sentinel-eval" in page and "make calibrate" in page


def test_staleness_notes_flag_old_thresholds_and_fallback_writer():
    assert se.staleness_notes(_inputs()) == []
    old = {"triage_confidence_min": 0.4, "high_priority_alert_probability": 0.25, "retrieval_similarity_min": 0.55}
    notes = se.staleness_notes(_inputs(report_thresholds=old, provider="extractive"))
    assert len(notes) == 2
    assert "0.40 / 0.25 / 0.55" in notes[0] and "extractive fallback" in notes[1]


def test_text_from_outputs_is_escaped():
    inputs = _inputs()
    inputs["report"]["pipeline"] = {"<script>x</script>": inputs["report"]["pipeline"]["gemini"]}
    page = se.render_html(inputs)
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page


def test_write_html_report_reads_saved_files(tmp_path: Path):
    inputs = _inputs()
    paths = {}
    for key in ("report", "dial", "calibration", "thresholds"):
        paths[key] = tmp_path / f"{key}.json"
        paths[key].write_text(json.dumps(inputs[key]), encoding="utf-8")
    loaded = se.load_report_inputs(paths["report"], paths["dial"], paths["calibration"], paths["thresholds"])
    assert all(loaded[k] is not None for k in paths)
    out = se.write_html_report(tmp_path / "page" / "eval_report.html", inputs=loaded)
    assert "How well SentinelDesk" in out.read_text(encoding="utf-8")


def test_load_report_inputs_falls_back_to_calibration_inside_the_report(tmp_path: Path):
    report = {"calibration": {"available": True, "heads": {"type": {}}}}
    (tmp_path / "r.json").write_text(json.dumps(report), encoding="utf-8")
    loaded = se.load_report_inputs(tmp_path / "r.json", tmp_path / "no.json", tmp_path / "no.json",
                                   tmp_path / "no.json")
    assert loaded["calibration"] == report["calibration"] and loaded["dial"] is None
