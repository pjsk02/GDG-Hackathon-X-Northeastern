"""Tests for Step 4: Manager page (with/without eval files, retrain) and label corrections."""

from __future__ import annotations

import json
from pathlib import Path

from sentinel import feedback, ticket_store
from shared.contracts import LabelCorrection, SentinelResult, TriageLabels
from shared.settings import Settings
from ui.pages.manager import compute_ticket_counts, compute_tier_rates


def _make_result(tier: str) -> SentinelResult:
    return SentinelResult(
        subject="S",
        body="B",
        detected_language="en",
        language_confidence=0.99,
        triage=TriageLabels(
            type="Incident",
            queue="Technical Support",
            priority="high",
            type_confidence=0.9,
            queue_confidence=0.8,
            priority_confidence=0.9,
            triage_confidence=0.8,
        ),
        escalation="AUTO_DRAFT" if tier == "AUTO_DRAFT" else "ESCALATE",
        tier=tier,  # type: ignore[arg-type]
    )


def test_compute_counts_and_tier_rates():
    ticket_store.reset()
    t1 = ticket_store.add_ticket("A", "B", source="customer")  # new -> open
    t2 = ticket_store.add_ticket("C", "D", source="preset")
    t3 = ticket_store.add_ticket("E", "F", source="preset")
    ticket_store.save_result(t2, _make_result("PAGE_ONCALL"))
    ticket_store.save_result(t3, _make_result("AUTO_DRAFT"))
    ticket_store.set_status(t3, "replied")

    tickets = ticket_store.list_tickets()
    counts = compute_ticket_counts(tickets)
    assert counts == {"open": 1, "in_progress": 1, "closed": 1, "total": 3}

    rates = compute_tier_rates(tickets)
    assert rates["PAGE_ONCALL"] == (1, 0.5)
    assert rates["AUTO_DRAFT"] == (1, 0.5)
    assert rates["AGENT_REVIEW"] == (0, 0.0)
    ticket_store.reset()


def test_manager_page_renders_without_data_files_and_retrains(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    ticket_store.reset()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(feedback, "get_settings", lambda: Settings(corrections_path=tmp_path / "corr.jsonl"))
    monkeypatch.setattr(
        feedback,
        "retrain_challenger",
        lambda: {
            "status": "promoted",
            "corrections_used": 2,
            "message": "Challenger beat champion.",
            "champion": {"type_macro_f1": 0.70},
            "challenger": {"type_macro_f1": 0.74},
        },
    )

    manager_page = Path(__file__).resolve().parents[1] / "ui/pages/manager.py"
    at = AppTest.from_file(manager_page, default_timeout=15)
    at.run()
    assert not at.exception
    info_text = "\n".join(i.value for i in at.info)
    assert "make dial" in info_text

    retrain_btn = next(b for b in at.button if b.key == "retrain_btn")
    retrain_btn.click().run()
    assert not at.exception
    md_text = "\n".join(m.value for m in at.markdown)
    assert "promoted" in md_text


def test_manager_page_renders_with_data_files(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    ticket_store.reset()
    eval_dir = tmp_path / "data" / "eval"
    (eval_dir / "latest").mkdir(parents=True)
    (eval_dir / "safety_dial.json").write_text(
        json.dumps([{"threshold": 0.5, "escalation_rate": 0.5, "hpi_recall": 0.85}]),
        encoding="utf-8",
    )
    (eval_dir / "latest" / "report.json").write_text(
        json.dumps({"type_macro_f1": 0.81, "hpi_recall": 0.89}),
        encoding="utf-8",
    )
    (eval_dir / "calibration.json").write_text(json.dumps({"ece": 0.03}), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(feedback, "get_settings", lambda: Settings(corrections_path=tmp_path / "corr.jsonl"))

    manager_page = Path(__file__).resolve().parents[1] / "ui/pages/manager.py"
    at = AppTest.from_file(manager_page, default_timeout=15)
    at.run()
    assert not at.exception
    metric_labels = {m.label for m in at.metric}
    assert "type_macro_f1" in metric_labels
    assert "hpi_recall" in metric_labels


def test_agent_panel_correct_labels_saves_correction(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    ticket_store.reset()
    corr_path = tmp_path / "corrections.jsonl"
    monkeypatch.setattr(feedback, "get_settings", lambda: Settings(corrections_path=corr_path))
    stub_agent = type(
        "_StubAgent",
        (),
        {"settings": Settings(llm_provider="extractive", llm_fallback="", warm_up=False)},
    )()
    monkeypatch.setattr("ui.shared.get_agent", lambda: stub_agent)

    tid = ticket_store.add_ticket("VPN down", "Gateway is down", source="preset")
    ticket_store.save_result(tid, _make_result("PAGE_ONCALL"))

    agent_page = Path(__file__).resolve().parents[1] / "ui/pages/agent.py"
    at = AppTest.from_file(agent_page, default_timeout=15)
    at.run()
    assert not at.exception

    # Update the corrected value in the "Correct labels" form and submit
    corr_input = next(t for t in at.text_input if t.key == f"corr_val_{tid}")
    corr_input.set_value("Problem")
    save_btn = next(b for b in at.button if b.label == "Save correction")
    save_btn.click().run()
    assert not at.exception

    saved = feedback.list_corrections()
    assert len(saved) == 1
    assert isinstance(saved[0], LabelCorrection)
    assert saved[0].ticket_id == tid
    assert saved[0].head == "type"
    assert saved[0].predicted == "Incident"
    assert saved[0].corrected == "Problem"
    ticket_store.reset()
