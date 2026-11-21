"""Offline tests for eval/sentinel_eval.py (owner A). A fake agent, tiny frames, no dataset, no index, no LLM."""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pandas as pd

from eval import sentinel_eval as se
from shared.contracts import GuardFinding


def _result(escalation="AUTO_DRAFT", tier=None, findings=(), flags=(), precedent_language="en", reasons=()):
    top = SimpleNamespace(ticket_id="TKT-00001", queue="IT Support", language=precedent_language)
    return SimpleNamespace(
        triage=SimpleNamespace(type="Incident", queue="IT Support", priority="high", triage_confidence=0.8),
        detected_language="en", escalation=escalation, tier=tier, escalation_reasons=list(reasons),
        grounded=True, refused=False, verified_citations=[1], rejected_citations=[], cited_ticket_ids=["TKT-00001"],
        top_similarity=0.7, precedents=[top], draft_reply="hello", latency_ms=10.0,
        stage_latency_ms={"generation_ms": 1.0, "retrieval_ms": 2.0}, provider="extractive", error=None,
        guard_findings=list(findings), injection_flags=list(flags), pii_masked=False, pii_found={},
    )


class FakeAgent:
    settings = SimpleNamespace(llm_provider="extractive")

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def triage(self, subject, body, provider=None):
        r = self.results[self.calls % len(self.results)]
        self.calls += 1
        return r


def _test_df(n=4):
    return pd.DataFrame({
        "ticket_id": [f"TKT-9{i:04d}" for i in range(n)], "subject": "s", "body": "b",
        "type": "Incident", "queue": "IT Support", "priority": "high", "language": "en",
    })


def test_pipeline_summary_reports_tiers_guards_and_injection():
    finding = GuardFinding(kind="number", text="48 hours", reason="not in any verified quote")
    agent = FakeAgent([
        _result(),
        _result("ESCALATE", "AGENT_REVIEW", findings=[finding]),
        _result("ESCALATE", "PAGE_ONCALL", flags=["ignore previous instructions"]),
        _result("ESCALATE", None),  # tier missing -> placeholder mapping (on-call)
    ])
    summary, df = se.run_pipeline_sample(agent, _test_df(4), 4, "extractive")
    assert summary["tier_auto_draft_rate"] == 0.25
    assert summary["tier_agent_review_rate"] == 0.25
    assert summary["tier_oncall_rate"] == 0.5
    assert summary["guard_findings_total"] == 1 and summary["guard_findings_per_ticket"] == 0.25
    assert summary["injection_hits"] == 1 and summary["injection_hit_rate"] == 0.25
    assert set(df["tier"]) == {"AUTO_DRAFT", "AGENT_REVIEW", "PAGE_ONCALL"}


def test_load_cases_merges_both_files_and_skips_missing(tmp_path):
    a = tmp_path / "sentinel_cases.jsonl"
    b = tmp_path / "cases_guardrails.jsonl"
    a.write_text(json.dumps({"id": "x", "body": "1", "expect_escalation": True}) + "\n\n", encoding="utf-8")
    b.write_text(json.dumps({"id": "x", "body": "2", "expect_escalation": False}) + "\n"
                 + json.dumps({"id": "y", "body": "3"}) + "\n", encoding="utf-8")
    cases = se.load_cases([a, b, tmp_path / "missing.jsonl"])
    assert [c["id"] for c in cases] == ["x", "cases_guardrails:x", "y"]
    assert [c["source"] for c in cases] == [a.name, b.name, b.name]
    assert se.load_cases([tmp_path / "missing.jsonl"]) == []


def test_check_case_expectations():
    num = GuardFinding(kind="money", text="5000 EUR", reason="unbacked")
    assert se.check_case({}, _result())["correct"] is None
    assert se.check_case({"expect_escalation": True}, _result("ESCALATE", "PAGE_ONCALL"))["correct"] is True
    assert se.check_case({"expect_escalation": True}, _result())["correct"] is False
    assert se.check_case({"expect_tier_not": ["PAGE_ONCALL"]}, _result("ESCALATE", "AGENT_REVIEW"))["correct"] is True
    assert se.check_case({"expect_tier_not": ["PAGE_ONCALL"]}, _result("ESCALATE", None))["correct"] is False
    assert se.check_case({"expect_precedent_language": "en"}, _result(precedent_language="de"))["correct"] is False
    assert se.check_case({"expect_guard_safe": True}, _result(findings=[num]))["correct"] is False
    assert se.check_case({"expect_guard_safe": True}, _result("ESCALATE", "AGENT_REVIEW", findings=[num]))["correct"]
    out = se.check_case({"expect_escalation": False, "expect_precedent_language": "en"},
                        _result("ESCALATE", "PAGE_ONCALL", precedent_language="de"))
    assert out["failed_checks"] == "escalation,precedent_language"


def test_behaviour_summary(tmp_path):
    cases = tmp_path / "c.jsonl"
    cases.write_text("\n".join(json.dumps(c) for c in [
        {"id": "a", "body": "x", "expect_escalation": True},
        {"id": "b", "body": "x", "expect_escalation": True},
        {"id": "c", "body": "x"},
    ]), encoding="utf-8")
    agent = FakeAgent([_result("ESCALATE", "PAGE_ONCALL", flags=["inj"]), _result(), _result()])
    summary, df = se.run_behaviour_cases(agent, "extractive", [cases])
    assert summary["cases"] == 3 and summary["scored_cases"] == 2
    assert summary["adversarial_escalation_rate"] == 0.5 and summary["behaviour_pass_rate"] == 0.5
    assert summary["case_injection_hits"] == 1


def test_calibration_is_skipped_cleanly_when_missing():
    out = se.calibration_section(object(), _test_df(), module="sentinel.no_such_calibration_module")
    assert out["available"] is False and "not found" in out["reason"]


def test_calibration_is_reported_when_present(monkeypatch):
    fake = types.ModuleType("fake_calibration")
    fake.report = lambda model, df: {"ece_before": 0.12, "ece_after": 0.03, "tickets": len(df)}
    monkeypatch.setitem(sys.modules, "fake_calibration", fake)
    out = se.calibration_section(object(), _test_df(3), module="fake_calibration")
    assert out == {"available": True, "split": "holdout", "ece_before": 0.12, "ece_after": 0.03, "tickets": 3}

    fake.report = lambda model, df: 1 / 0
    assert se.calibration_section(object(), _test_df(), module="fake_calibration")["available"] is False


def test_report_is_always_written_to_latest(tmp_path):
    run_dir, latest = tmp_path / "sentinel-1", tmp_path / "latest"
    path = se.write_report(run_dir, {"triage": {"type_macro_f1": 0.9}}, latest_dir=latest)
    assert path == latest / "report.json"
    assert json.loads(path.read_text()) == json.loads((run_dir / "report.json").read_text())


def test_new_behaviour_cases_are_present():
    ids = {c["id"] for c in se.load_cases([se.CASES])}
    assert {"xling-de-printer", "trap-reply-numbers", "adv-injection-de", "outage-empty-subject",
            "routine-password-reset"} <= ids
