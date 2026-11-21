"""group_burst: linked tickets, shared precedent, and the EN/DE status text (template, no LLM)."""

import pytest

from sentinel.incidents import Incident, group_burst, resolution_summary, status_text, text_language
from sentinel.outage import OutageAlert
from sentinel.ticket_store import TicketRecord
from shared.contracts import Precedent, SentinelResult, TriageLabels

EN_ANSWER = ("Dear <name>, thank you for reaching out. Could you send the error message? "
             "We restarted the VPN gateway and renewed the expired certificate. Remote access was restored for all "
             "users. Best regards")
DE_ANSWER = ("Sehr geehrte Damen und Herren, vielen Dank für Ihre Nachricht. Können Sie uns die Fehlermeldung senden? "
             "Wir haben das abgelaufene Zertifikat des VPN-Gateways erneuert. Der Fernzugriff ist wieder für alle "
             "Nutzer verfügbar.")


def _precedent(pid, similarity=0.5, answer=EN_ANSWER, language="en"):
    return Precedent(ticket_id=pid, similarity=similarity, subject="VPN", body_snippet="b", answer=answer,
                     type="Incident", queue="IT Support", priority="high", language=language)


def _ticket(tid, created_at, precedents, language="en", subject=None):
    result = SentinelResult(
        subject=subject or f"VPN down {tid}", body="VPN down", detected_language=language, language_confidence=1.0,
        triage=TriageLabels(type="Incident", queue="IT Support", priority="high", type_confidence=1,
                            queue_confidence=1, priority_confidence=1, triage_confidence=1),
        escalation="ESCALATE", precedents=precedents,
    )
    return TicketRecord(ticket_id=tid, subject=subject or f"VPN down {tid}", body="VPN down", status="triaged",
                        created_at=created_at, result=result)


def _alert(ids=(), subjects=(), shared=(), system="VPN"):
    return OutageAlert(ticket_count=len(ids) or len(subjects), shared_precedents=list(shared),
                       subjects=list(subjects), since_seconds=60.0, system=system, ticket_ids=list(ids))


@pytest.fixture
def tickets():
    common = _precedent("TKT-0042", 0.6)
    return [
        _ticket("SD-1005", 1005.0, [_precedent("TKT-0001", 0.9), common]),
        _ticket("SD-1003", 1003.0, [common, _precedent("TKT-0002", 0.7)]),
        _ticket("SD-1006", 1006.0, [_precedent("TKT-0003", 0.8), common], language="de"),
        _ticket("SD-1001", 1001.0, [_precedent("TKT-0009")], subject="CSV export"),  # not part of the burst
    ]


def test_groups_the_alert_tickets_in_arrival_order(tickets):
    inc = group_burst(_alert(ids=["SD-1005", "SD-1003", "SD-1006"]), tickets)
    assert isinstance(inc, Incident)
    assert inc.incident_id == "INC-1003"
    assert inc.ticket_ids == ["SD-1003", "SD-1005", "SD-1006"]
    assert inc.title == "VPN outage" and inc.system == "VPN"
    assert inc.first_seen == 1003.0
    assert inc.language == "en"  # 2 of 3 English


def test_shared_precedent_is_the_most_retrieved_one(tickets):
    inc = group_burst(_alert(ids=["SD-1003", "SD-1005", "SD-1006"]), tickets)
    assert inc.shared_precedent.ticket_id == "TKT-0042"  # in all three, though never the most similar


def test_alert_shared_precedents_win(tickets):
    inc = group_burst(_alert(ids=["SD-1003", "SD-1005", "SD-1006"], shared=["TKT-0002"]), tickets)
    assert inc.shared_precedent.ticket_id == "TKT-0002"


def test_links_by_subject_when_the_alert_has_no_ids(tickets):
    inc = group_burst(_alert(subjects=["VPN down SD-1003", "VPN down SD-1006"]), tickets)
    assert inc.ticket_ids == ["SD-1003", "SD-1006"]


def test_subject_fallback_ignores_an_earlier_burst_with_the_same_subjects():
    # The demo burst fired twice: same subjects, the alert is about the second burst.
    old = [_ticket(f"SD-10{i}", float(i), [_precedent("TKT-1")], subject=f"VPN down {i}") for i in range(3)]
    new = [_ticket(f"SD-20{i}", 100.0 + i, [_precedent("TKT-1")], subject=f"VPN down {i}") for i in range(3)]
    inc = group_burst(_alert(subjects=[f"VPN down {i}" for i in range(3)]), old + new)
    assert inc.ticket_ids == ["SD-200", "SD-201", "SD-202"]


def test_subject_fallback_keeps_repeated_subjects():
    tickets = [_ticket(f"SD-10{i}", float(i), [_precedent("TKT-1")], subject="VPN down") for i in range(4)]
    inc = group_burst(_alert(subjects=["VPN down", "VPN down", "VPN down"]), tickets)
    assert inc.ticket_ids == ["SD-101", "SD-102", "SD-103"]


def test_no_matching_tickets_is_an_error(tickets):
    with pytest.raises(ValueError):
        group_burst(_alert(ids=["SD-9999"]), tickets)


def test_status_texts_quote_the_resolution_in_its_language(tickets):
    inc = group_burst(_alert(ids=["SD-1003", "SD-1005", "SD-1006"]), tickets)
    en, de = inc.status_updates["en"], inc.status_updates["de"]
    assert inc.status_update == en
    assert "INC-1003" in en and "VPN" in en and "3 customers" in en
    assert '"We restarted the VPN gateway and renewed the expired certificate.' in en
    assert "<name>" not in en and "?" not in en and "Dear" not in en
    # The precedent is English, so the German text names it instead of mixing languages.
    assert "Statusmeldung INC-1003" in de and "3 Kunden" in de
    assert "TKT-0042" in de and "IT Support" in de and "We restarted" not in de


def test_german_resolution_is_quoted_in_the_german_text():
    tickets = [_ticket(f"SD-10{i}", float(i), [_precedent("TKT-7", answer=DE_ANSWER, language="de")], language="de")
               for i in range(3)]
    inc = group_burst(_alert(ids=[t.ticket_id for t in tickets]), tickets)
    assert inc.language == "de" and inc.status_update == inc.status_updates["de"]
    assert "„Wir haben das abgelaufene Zertifikat" in inc.status_updates["de"]
    assert "Wir haben" not in inc.status_updates["en"]


def test_no_system_and_no_precedent():
    text = status_text("en", "INC-1", None, 4, 0.0, None)
    assert "a major issue" in text and "4 customers" in text and "similar past case" not in text
    text_de = status_text("de", "INC-1", None, 4, 0.0, None)
    assert "einer größeren Störung" in text_de


def test_resolution_summary_keeps_clean_sentences_only():
    assert resolution_summary(EN_ANSWER) == (
        "We restarted the VPN gateway and renewed the expired certificate. "
        "Remote access was restored for all users."
    )
    assert resolution_summary("Dear <name>, could you call me at <tel_num>? I will check.") == ""
    assert len(resolution_summary("We fixed it. " * 100)) <= 280


def test_text_language():
    assert text_language("We restarted the gateway and the service is back.") == "en"
    assert text_language("Wir haben das Gateway neu gestartet und der Dienst ist wieder da.") == "de"
