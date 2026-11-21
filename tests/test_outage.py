"""OutageTracker: the simulator's VPN burst (EN + DE, no shared precedents) raises one alert that stays up."""

from sentinel.outage import OutageTracker, detect_systems
from sentinel.simulator import DEMO_TICKETS
from shared.contracts import Precedent, SentinelResult, TriageLabels


def _result(subject, body, type_="Incident", priority="high", precedents=(), language="en"):
    return SentinelResult(
        subject=subject, body=body, detected_language=language, language_confidence=1.0,
        triage=TriageLabels(type=type_, queue="IT Support", priority=priority, type_confidence=1,
                            queue_confidence=1, priority_confidence=1, triage_confidence=1),
        escalation="ESCALATE",
        precedents=[
            Precedent(ticket_id=p, similarity=0.5, subject="s", body_snippet="b", answer="a", type="Incident",
                      queue="IT Support", priority="high", language="en")
            for p in precedents
        ],
    )


def _demo(kind_prefix):
    return [t for t in DEMO_TICKETS if t["kind"].startswith(kind_prefix)]


def test_detect_systems_english_and_german():
    assert detect_systems("Our VPN is down") == {"VPN"}
    assert detect_systems("VPN-Ausfall im Netzwerk") == {"VPN", "network"}
    assert detect_systems("E-Mail Postfach nicht erreichbar") == {"email"}
    assert detect_systems("Single sign-on fails at login") == {"login"}
    # Whole words only: "rapid" is not "api", "happiness" not "api", "servers" not a system at all.
    assert detect_systems("rapid happiness on our servers") == frozenset()


def test_simulator_burst_raises_one_vpn_alert_without_shared_precedents():
    tracker = OutageTracker()
    alerts = []
    # Distinct precedents for every ticket: with 22k indexed tickets that is the realistic case.
    for i, t in enumerate(_demo("outage")):
        alerts.append(tracker.observe(_result(t["subject"], t["body"], precedents=[f"TKT-{i}{j}" for j in range(5)]),
                                      now=100.0 + i, ticket_id=f"SD-{i}"))
    assert alerts[:2] == [None, None]
    alert = alerts[2]
    assert alert is not None and alert.ticket_count == 3 and alert.system == "VPN"
    assert alert.ticket_ids == ["SD-0", "SD-1", "SD-2"]
    assert "VPN" in alert.headline and "3 tickets" in alert.headline


def test_alert_stays_up_when_unrelated_tickets_follow():
    tracker = OutageTracker()
    for i, t in enumerate(_demo("outage")):
        tracker.observe(_result(t["subject"], t["body"]), now=100.0 + i)
    # The refund trap is a high Problem and a routine ticket was labelled Incident: both count as incidents,
    # neither is about the VPN.
    refund = _demo("refund_trap")[0]
    tracker.observe(_result(refund["subject"], refund["body"], type_="Problem"), now=110.0)
    alert = tracker.observe(_result("CSV export of usage reports", "routine", priority="medium"), now=111.0)
    assert alert is not None and alert.ticket_count == 3 and alert.system == "VPN"
    assert tracker.check(now=112.0) is not None


def test_routine_tickets_do_not_alert():
    tracker = OutageTracker()
    for i, t in enumerate(_demo("routine")):
        assert tracker.observe(_result(t["subject"], t["body"], type_="Incident"), now=100.0 + i) is None


def test_non_incident_types_are_ignored():
    tracker = OutageTracker()
    for i in range(4):
        assert tracker.observe(_result(f"VPN question {i}", "How do I set up VPN?", type_="Request"), now=100.0 + i) \
            is None


def test_window_expires():
    tracker = OutageTracker(window_seconds=60)
    for i, t in enumerate(_demo("outage")[:2]):
        tracker.observe(_result(t["subject"], t["body"]), now=100.0 + i)
    t = _demo("outage")[2]
    assert tracker.observe(_result(t["subject"], t["body"]), now=500.0) is None


def test_precedent_overlap_still_links_tickets_without_a_known_system():
    tracker = OutageTracker()
    shared = ["TKT-1", "TKT-2", "TKT-3", "TKT-4"]
    alert = None
    for i in range(3):
        alert = tracker.observe(_result(f"Ticket {i}", "Reports are empty", precedents=shared + [f"TKT-x{i}"]),
                                now=100.0 + i)
    assert alert is not None and alert.system is None
    assert alert.shared_precedents == shared
    assert "same historical failure" in alert.headline


def test_linking_is_transitive():
    # A~B by system, B~C by precedents: all three are one burst.
    tracker = OutageTracker()
    tracker.observe(_result("VPN down", "vpn", precedents=["TKT-a"]), now=100.0)
    tracker.observe(_result("VPN slow", "vpn", precedents=["TKT-1", "TKT-2", "TKT-3"]), now=101.0)
    alert = tracker.observe(_result("Reports fail", "x", precedents=["TKT-1", "TKT-2", "TKT-3"]), now=102.0)
    assert alert is not None and alert.ticket_count == 3


def test_reset():
    tracker = OutageTracker()
    for i, t in enumerate(_demo("outage")):
        tracker.observe(_result(t["subject"], t["body"]), now=100.0 + i)
    tracker.reset()
    assert tracker.check(now=103.0) is None
