"""Ingest: the idempotent front door. external_id is the dedupe anchor - a retried
webhook, a re-polled IMAP message, or a double-clicked form all converge to one ticket."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agent import audit
from .models import Ticket


def ingest_ticket(session: Session, raw: dict) -> tuple[Ticket, bool]:
    """Returns (ticket, created). created=False means this delivery was a duplicate."""
    external_id = raw["external_id"]
    existing = session.query(Ticket).filter(Ticket.external_id == external_id).one_or_none()
    if existing:
        return existing, False
    ticket = Ticket(external_id=external_id, subject=raw["subject"], body=raw["body"],
                    customer_email=raw["customer_email"], status="new")
    session.add(ticket)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return (session.query(Ticket).filter(Ticket.external_id == external_id).one(),
                False)
    audit(session, ticket.id, "system", "ingested", {"external_id": external_id})
    return ticket, True
