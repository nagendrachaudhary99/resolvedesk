"""Fake payment provider with REAL idempotency semantics: its ledger enforces a unique
idempotency key exactly like Stripe's API does, so crash/retry behavior in tests is
genuine, not simulated. A fault hook (RD_PAYMENT_CRASH_AFTER_CHARGE=1) kills the call
after the charge commits but before the caller can record success - the exact
mid-refund crash the failure-injection tests verify recovery from."""
import os

from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import PaymentLedger
from ..ports import PaymentProvider


class ChargeCommittedCrash(Exception):
    """Raised when the fault hook fires: the money moved, the caller doesn't know."""


class FakePaymentProvider:
    name = "fake-ledger"

    def refund(self, *, idempotency_key: str, ticket_id: str, amount_cents: int) -> str:
        session = db.session()
        try:
            existing = (
                session.query(PaymentLedger)
                .filter(PaymentLedger.idempotency_key == idempotency_key)
                .one_or_none()
            )
            if existing:
                return existing.id  # retry: already charged, never again
            row = PaymentLedger(idempotency_key=idempotency_key, ticket_id=ticket_id,
                                amount_cents=amount_cents)
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()  # lost a race with a twin worker - same outcome
                existing = (
                    session.query(PaymentLedger)
                    .filter(PaymentLedger.idempotency_key == idempotency_key)
                    .one()
                )
                return existing.id
            if os.environ.get("RD_PAYMENT_CRASH_AFTER_CHARGE") == "1":
                raise ChargeCommittedCrash("fault: crashed after charge committed")
            return row.id
        finally:
            session.close()
