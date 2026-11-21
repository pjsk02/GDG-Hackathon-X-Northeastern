"""Demo ticket burst for the queue page (owner: Rithwik, role C).

    from sentinel.simulator import DEMO_TICKETS, fire
    ids = fire(queue, n=10)        # adds the tickets to sentinel.ticket_store and submits them as one burst

DEMO_TICKETS (10): three VPN outage reports that form a burst (OutageTracker should flag them), a refund demand
that must be escalated, three German tickets (one of them part of the outage), and routine questions that should
wait behind the urgent ones. Arrival order deliberately puts routine tickets first, so the queue's reordering shows.
"""

from __future__ import annotations

from sentinel import ticket_store

# Worded like the dataset's tickets so the real triage model labels them as intended (checked against the model
# trained by `make sentinel-train`): the outages come out as high-priority Incidents (rank 0), the refund demand as a
# high Problem (rank 0, arrives after the outages), the routine tickets as medium/low.
DEMO_TICKETS: list[dict[str, str]] = [
    {
        "kind": "routine",
        "subject": "CSV export of usage reports",
        "body": "Dear Support,\n\nI would like to know if the usage reports can be exported in CSV format. This is a "
                "general question for our planning, there is no urgency.\n\nKind regards",
    },
    {
        "kind": "routine_de",
        "subject": "Änderung der Rechnungsadresse",
        "body": "Sehr geehrtes Team,\n\nkönnten Sie mir bitte mitteilen, wie ich die Rechnungsadresse in unserem Konto "
                "ändern kann? Vielen Dank für Ihre Unterstützung.\n\nMit freundlichen Grüßen",
    },
    {
        "kind": "outage",
        "subject": "Urgent: VPN outage affecting all users",
        "body": "Dear Support Team,\n\nOur corporate VPN has been completely down since this morning. None of our "
                "employees can connect, the client fails during authentication, and critical business operations are "
                "disrupted. We have already restarted the VPN gateway and checked the firewall without success. "
                "Please investigate this urgent incident immediately.\n\nBest regards",
    },
    {
        "kind": "routine",
        "subject": "Adding a new team member",
        "body": "Could you please provide guidance on how to add a new colleague to our analytics workspace with viewer "
                "permissions? Thank you for your assistance.",
    },
    {
        "kind": "outage",
        "subject": "VPN connection failure - critical",
        "body": "We are experiencing a critical VPN connection failure across our network. Since 9 AM users cannot "
                "reach internal servers and the authentication times out. This is causing a major service disruption "
                "for the whole organization. Immediate assistance is required.",
    },
    {
        "kind": "outage_de",
        "subject": "Dringend: VPN-Ausfall im gesamten Unternehmen",
        "body": "Sehr geehrtes Support-Team,\n\nseit heute Morgen ist unser VPN vollständig ausgefallen. Keiner unserer "
                "Mitarbeiter kann sich verbinden, die Authentifizierung bricht mit einem Timeout ab und kritische "
                "Geschäftsprozesse sind unterbrochen. Neustarts des Gateways haben nicht geholfen. Bitte beheben Sie "
                "diesen dringenden Vorfall sofort.\n\nMit freundlichen Grüßen",
    },
    {
        "kind": "refund_trap",
        "subject": "Refund demand for double billing",
        "body": "Our company was billed twice for the annual plan. We expect a full refund of the duplicate charge "
                "within 24 hours, or we will involve our lawyer. Confirm the refund amount in your response.",
    },
    {
        "kind": "routine",
        "subject": "Copy of March invoice",
        "body": "Could you please send a copy of our March invoice? Our accounting team needs it for documentation.",
    },
    {
        "kind": "routine_de",
        "subject": "Frage zum Passwort",
        "body": "Hallo, wie kann ich mein Passwort ändern? Es ist nicht dringend, ich möchte es nur regelmäßig "
                "aktualisieren. Danke!",
    },
    {
        "kind": "routine",
        "subject": "Training materials for new staff",
        "body": "Could you please provide guidance on where to find training materials for our new staff members? "
                "Thank you for your assistance.",
    },
]


def fire(queue, n: int = 10) -> list[str]:
    """Add the first `n` demo tickets to the ticket store and submit them to `queue` as one burst."""
    tickets = DEMO_TICKETS[: max(0, n)]
    ids = [ticket_store.add_ticket(t["subject"], t["body"], source="simulator") for t in tickets]
    if hasattr(queue, "submit_many"):
        queue.submit_many(ids)
    else:  # any queue with the contract interface only
        for ticket_id in ids:
            queue.submit(ticket_id)
    return ids
