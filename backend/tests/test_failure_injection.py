"""Failure injection: real crashes and faults, verified recovery. These tests are the
reason the outbox + idempotency design exists."""
import pytest

from app import db
from app.agent import enqueue, process_ticket
from app.ingest import ingest_ticket
from app.models import Approval, AuditEvent, Draft, OutboxEvent, PaymentLedger, Ticket
from app.outbox import run_once
from app.ports import LLMError


def _approved_refund(session, llm, ext="fi-1"):
    ticket, _ = ingest_ticket(session, {
        "external_id": ext, "subject": "Refund $75.00",
        "body": "Refund my $75.00 charge please, I want my money back.",
        "customer_email": "nina@acme.io"})
    process_ticket(session, ticket, llm)
    for a in session.query(Approval).filter_by(ticket_id=ticket.id).all():
        a.status = "approved"
        if a.action_type == "refund":
            enqueue(session, ticket.id, "refund",
                    {"amount_cents": a.payload["amount_cents"]})
        else:
            enqueue(session, ticket.id, "send_reply",
                    {"to": a.payload["to"], "subject": a.payload["subject"],
                     "body": a.payload["body"]})
    session.commit()
    return ticket


def test_worker_crash_mid_refund_recovers_without_double_charge(session, llm, monkeypatch):
    """Kill the payment call AFTER the charge commits but before the outbox is updated.
    The retry must see the ledger row and finish without charging again."""
    t = _approved_refund(session, llm)
    monkeypatch.setenv("RD_PAYMENT_CRASH_AFTER_CHARGE", "1")
    outcomes = run_once(db.session)
    assert outcomes["retry"] >= 1  # the refund event "crashed"
    charges = session.query(PaymentLedger).filter_by(ticket_id=t.id).all()
    assert len(charges) == 1  # the money moved once
    assert any(e.status == "pending" for e in session.query(OutboxEvent)
               .filter_by(event_type="refund"))

    monkeypatch.delenv("RD_PAYMENT_CRASH_AFTER_CHARGE")
    outcomes = run_once(db.session)
    charges = session.query(PaymentLedger).filter_by(ticket_id=t.id).all()
    assert len(charges) == 1  # recovery charged NOTHING new
    session.expire_all()
    refund_events = session.query(OutboxEvent).filter_by(event_type="refund").all()
    assert all(e.status == "done" for e in refund_events)
    actions = {e.action for e in session.query(AuditEvent).filter_by(ticket_id=t.id)}
    assert "refund_executed" in actions


class GarbageLLM:
    """LLM that returns malformed output - the pipeline must park, not crash."""
    name = "garbage-v0"

    def complete_json(self, task, payload):
        if task == "classify":
            return {"category": "not_a_real_category", "confidence": "high"}
        raise LLMError("unexpected eof while parsing")


class TimeoutLLM:
    name = "timeout-v0"

    def complete_json(self, task, payload):
        raise LLMError("read timed out after 30s")


def test_garbage_llm_parks_ticket_in_needs_review(session):
    ticket, _ = ingest_ticket(session, {
        "external_id": "fi-garbage", "subject": "Any", "body": "Anything at all",
        "customer_email": "x@y.co"})
    result = process_ticket(session, ticket, GarbageLLM())
    session.commit()
    assert result is None
    assert ticket.status == "needs_review"
    assert session.query(Draft).filter_by(ticket_id=ticket.id).count() == 0
    actions = {e.action for e in session.query(AuditEvent).filter_by(ticket_id=ticket.id)}
    assert "llm_error" in actions


def test_timeout_llm_parks_ticket(session):
    ticket, _ = ingest_ticket(session, {
        "external_id": "fi-timeout", "subject": "Help", "body": "Need help with billing",
        "customer_email": "x@y.co"})
    process_ticket(session, ticket, TimeoutLLM())
    session.commit()
    assert ticket.status == "needs_review"
    # Nothing half-written: no draft, no approvals, no outbox events.
    assert session.query(Draft).filter_by(ticket_id=ticket.id).count() == 0
    assert session.query(Approval).filter_by(ticket_id=ticket.id).count() == 0
    assert session.query(OutboxEvent).filter_by(ticket_id=ticket.id).count() == 0


def test_unknown_event_type_fails_loudly_after_retry_cap(session):
    ev = enqueue(session, "ticket-z", "teleport", {"to": "mars"})
    session.commit()
    for _ in range(6):
        run_once(db.session)
    session.expire_all()
    ev = session.query(OutboxEvent).filter_by(id=ev.id).one()
    assert ev.status == "failed"
    assert ev.last_error and "unknown event_type" in ev.last_error
