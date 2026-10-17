"""Outbox worker. Claims events with SELECT ... FOR UPDATE SKIP LOCKED (so multiple
workers can run safely), executes the handler, and records the outcome. Every handler
is idempotent, so any retry - crash, duplicate claim, redeploy - converges to exactly
one real-world effect per event."""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .adapters import get_payment_provider, get_reply_channel
from .config import get_settings
from .adapters.fake_payments import ChargeCommittedCrash
from .models import OutboxEvent, Ticket

log = logging.getLogger("resolvedesk.outbox")


def claim_batch(session: Session, size: int = 10) -> list[str]:
    """Atomically claim up to `size` pending events. Returns claimed ids."""
    rows = session.execute(
        text(
            """
            UPDATE outbox_events
            SET status = 'processing', attempts = attempts + 1
            WHERE id IN (
                SELECT id FROM outbox_events
                WHERE status = 'pending' AND attempts < :max_attempts
                ORDER BY created_at
                LIMIT :size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """
        ),
        {"size": size, "max_attempts": get_settings().outbox_max_attempts},
    ).fetchall()
    return [r.id for r in rows]


def _audit(db_session_factory, ticket_id: str, actor: str, action: str, detail: dict) -> None:
    from .agent import audit

    s = db_session_factory()
    try:
        audit(s, ticket_id, actor, action, detail)
        s.commit()
    finally:
        s.close()


def _maybe_finalize(db_session_factory, ticket_id: str) -> None:
    """Ticket is resolved when no pending outbox events and no pending approvals remain."""
    from .models import Approval

    s = db_session_factory()
    try:
        pending_events = s.query(OutboxEvent).filter(
            OutboxEvent.ticket_id == ticket_id,
            OutboxEvent.status.in_(["pending", "processing"])).count()
        pending_approvals = s.query(Approval).filter(
            Approval.ticket_id == ticket_id, Approval.status == "pending").count()
        if pending_events == 0 and pending_approvals == 0:
            t = s.get(Ticket, ticket_id)
            if t and t.status in ("auto_resolved", "pending_approval"):
                t.status = "resolved"
                s.commit()
    finally:
        s.close()


def execute_event(db_session_factory, event_id: str) -> str:
    """Execute one claimed event in its own transaction. Returns done|retry|failed."""
    reply_channel = get_reply_channel()
    payments = get_payment_provider()

    s = db_session_factory()
    try:
        ev = s.get(OutboxEvent, event_id)
        if ev is None or ev.status == "done":
            return "done"
        try:
            if ev.event_type == "send_reply":
                provider_id = reply_channel.send(
                    ev.payload["to"], ev.payload["subject"], ev.payload["body"],
                    ev.idempotency_key)
                _audit(db_session_factory, ev.ticket_id, "system", "reply_sent",
                       {"provider": reply_channel.name, "provider_id": provider_id})
            elif ev.event_type == "refund":
                provider_id = payments.refund(
                    idempotency_key=ev.idempotency_key, ticket_id=ev.ticket_id,
                    amount_cents=int(ev.payload["amount_cents"]))
                _audit(db_session_factory, ev.ticket_id, "system", "refund_executed",
                       {"provider": payments.name, "provider_id": provider_id,
                        "amount_cents": ev.payload["amount_cents"]})
            else:
                raise ValueError(f"unknown event_type {ev.event_type}")
        except ChargeCommittedCrash as e:
            # The money moved but we don't know it yet. Leave pending: the retry's
            # idempotency check sees the ledger row and completes without charging again.
            ev.status = "pending"
            ev.last_error = str(e)
            s.commit()
            log.warning("event %s crashed after side effect; retry will dedupe", ev.id)
            return "retry"
        except Exception as e:  # transient or permanent - retry until attempts cap
            ev.last_error = str(e)
            if ev.attempts >= get_settings().outbox_max_attempts:
                ev.status = "failed"
                t = s.get(Ticket, ev.ticket_id)
                if t:
                    t.status = "needs_review"
                s.commit()
                _audit(db_session_factory, ev.ticket_id, "system", "event_failed",
                       {"event_type": ev.event_type, "error": str(e)})
                return "failed"
            ev.status = "pending"
            s.commit()
            return "retry"

        ev.status = "done"
        ev.processed_at = datetime.now(timezone.utc)
        s.commit()
        _maybe_finalize(db_session_factory, ev.ticket_id)
        return "done"
    finally:
        s.close()


def run_once(db_session_factory, batch_size: int = 10) -> dict[str, int]:
    """Claim and execute one batch. Returns outcome counts."""
    s = db_session_factory()
    try:
        ids = claim_batch(s, batch_size)
        s.commit()
    finally:
        s.close()
    counts = {"done": 0, "retry": 0, "failed": 0}
    for event_id in ids:
        counts[execute_event(db_session_factory, event_id)] += 1
    return counts
