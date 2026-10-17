"""Integration: idempotency at every layer - ingest, outbox enqueue, refund, decisions."""
import pytest

from app import db
from app.agent import enqueue, process_ticket
from app.ingest import ingest_ticket
from app.models import Approval, OutboxEvent, PaymentLedger, Ticket
from app.outbox import run_once


def _refund_ticket(session, llm):
    ticket, _ = ingest_ticket(session, {
        "external_id": "idem-1", "subject": "Refund $49.00",
        "body": "Please refund my $49.00 charge, I want my money back.",
        "customer_email": "sam@acme.io"})
    process_ticket(session, ticket, llm)
    session.commit()
    return ticket


def _approve_all(session):
    for a in session.query(Approval).filter_by(status="pending").all():
        a.status = "approved"
        if a.action_type == "refund":
            enqueue(session, a.ticket_id, "refund",
                    {"amount_cents": a.payload["amount_cents"]})
        else:
            enqueue(session, a.ticket_id, "send_reply",
                    {"to": a.payload["to"], "subject": a.payload["subject"],
                     "body": a.payload["body"]})
    session.commit()


def test_duplicate_ingest_same_external_id(session, llm):
    raw = {"external_id": "dup-1", "subject": "Invoice?",
           "body": "Can I get an invoice copy?", "customer_email": "a@b.co"}
    t1, c1 = ingest_ticket(session, raw)
    session.commit()
    t2, c2 = ingest_ticket(session, raw)
    assert c1 and not c2
    assert t1.id == t2.id
    assert session.query(Ticket).filter_by(external_id="dup-1").count() == 1


def test_enqueue_dedupes_by_idempotency_key(session):
    e1 = enqueue(session, "ticket-x", "refund", {"amount_cents": 100})
    e2 = enqueue(session, "ticket-x", "refund", {"amount_cents": 100})
    assert e1.id == e2.id
    session.commit()
    assert session.query(OutboxEvent).filter_by(ticket_id="ticket-x").count() == 1


def test_worker_retry_never_double_charges(session, llm):
    t = _refund_ticket(session, llm)
    _approve_all(session)
    run_once(db.session)   # first pass
    run_once(db.session)   # second pass (nothing left, but be sure)
    run_once(db.session)
    refunds = session.query(PaymentLedger).filter_by(ticket_id=t.id).all()
    assert len(refunds) == 1
    assert refunds[0].amount_cents == 4900
    assert all(e.status == "done" for e in session.query(OutboxEvent).all())
    session.refresh(t)
    assert t.status == "resolved"


def test_api_duplicate_post_returns_duplicate(client):
    raw = {"subject": "Invoice copy", "body": "Please resend my invoice PDF.",
           "customer_email": "dup@acme.io", "external_id": "api-dup-1"}
    r1 = client.post("/tickets", json=raw, headers={"X-API-Token": "dev-token"})
    r2 = client.post("/tickets", json=raw, headers={"X-API-Token": "dev-token"})
    assert r1.status_code == 201
    assert r2.json()["duplicate"] is True
    assert r1.json()["ticket_id"] == r2.json()["ticket_id"]


def test_decision_twice_conflicts(client):
    r = client.post("/tickets", json={
        "subject": "Refund $25.00", "body": "Refund my $25.00 charge please.",
        "customer_email": "kai@acme.io"}, headers={"X-API-Token": "dev-token"})
    tid = r.json()["ticket_id"]
    approvals = client.get("/approvals").json()
    mine = [a for a in approvals if a["ticket_id"] == tid]
    assert mine
    aid = mine[0]["id"]
    d1 = client.post(f"/approvals/{aid}/decision",
                     json={"decision": "approve", "decided_by": "tester"},
                     headers={"X-API-Token": "dev-token"})
    d2 = client.post(f"/approvals/{aid}/decision",
                     json={"decision": "approve", "decided_by": "tester"},
                     headers={"X-API-Token": "dev-token"})
    assert d1.status_code == 200
    assert d2.status_code == 409
