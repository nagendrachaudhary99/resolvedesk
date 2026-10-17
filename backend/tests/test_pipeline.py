"""Integration: the full pipeline against real Postgres."""
from app.agent import process_ticket
from app.ingest import ingest_ticket
from app.models import Approval, AuditEvent, Draft, OutboxEvent, Ticket
from app.seed import generate_tickets


def _make(session, llm, subject, body, email="ava@acme.io", ext=None):
    ticket, created = ingest_ticket(session, {
        "external_id": ext or f"t-{subject[:12]}", "subject": subject, "body": body,
        "customer_email": email})
    assert created
    process_ticket(session, ticket, llm)
    session.commit()
    return ticket


def test_refund_routes_to_human_with_two_approvals(session, llm):
    t = _make(session, llm, "Charged twice",
              "I was charged twice, two charges of $49.00. Please refund the duplicate.")
    assert t.status == "pending_approval"
    assert t.category == "refund_request"
    approvals = session.query(Approval).filter_by(ticket_id=t.id).all()
    kinds = sorted(a.action_type for a in approvals)
    assert kinds == ["refund", "send_reply"]
    refund = next(a for a in approvals if a.action_type == "refund")
    assert refund.payload["amount_cents"] == 4900


def test_how_to_auto_resolves(session, llm):
    t = _make(session, llm, "Export data?",
              "How do I export all our workspace data as JSON before renewal?")
    assert t.status == "auto_resolved"
    assert t.category == "how_to"
    events = session.query(OutboxEvent).filter_by(ticket_id=t.id).all()
    assert [e.event_type for e in events] == ["send_reply"]
    draft = session.query(Draft).filter_by(ticket_id=t.id).one()
    assert draft.grounded_ok and draft.citations


def test_money_never_auto_resolves_even_when_confident(session, llm):
    t = _make(session, llm, "Refund please",
              "Refund my $29.00 charge from last week please. I want my money back, refund it.")
    assert t.status == "pending_approval"  # confidence high, but money => human


def test_audit_trail_complete(session, llm):
    t = _make(session, llm, "How do I export data?",
              "How do I export all our workspace data as JSON before our renewal?")
    actions = {e.action for e in session.query(AuditEvent).filter_by(ticket_id=t.id)}
    assert {"ingested", "classified", "drafted", "routed_auto"} <= actions


def test_seeded_batch_processes_cleanly(session, llm):
    for raw in generate_tickets(count=10, offset=0):
        ticket, _ = ingest_ticket(session, raw)
        process_ticket(session, ticket, llm)
        session.commit()
    total = session.query(Ticket).count()
    assert total == 10
    assert all(t.status in ("auto_resolved", "pending_approval")
               for t in session.query(Ticket).all())
