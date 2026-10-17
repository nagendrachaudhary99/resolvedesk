"""Real Stripe adapter (official stripe-python SDK). Enabled when STRIPE_API_KEY is set.
Stripe enforces idempotency keys server-side, matching the outbox contract. The payload
must carry a Stripe charge id (`charge`) - in a wired deployment that comes from the
billing system at ingest time. Never active by default; the fake ledger is."""
import os

from ..ports import PaymentProvider


class StripePaymentProvider:
    name = "stripe"

    def __init__(self) -> None:
        import stripe  # imported lazily so the SDK is optional in dev/test

        stripe.api_key = os.environ["STRIPE_API_KEY"]
        self._stripe = stripe

    def refund(self, *, idempotency_key: str, ticket_id: str, amount_cents: int) -> str:
        charge = os.environ.get("RD_STRIPE_TEST_CHARGE")
        if not charge:
            raise RuntimeError("Stripe adapter needs a charge id (RD_STRIPE_TEST_CHARGE "
                               "for the prototype; a real deployment carries it on the ticket)")
        refund = self._stripe.Refund.create(
            charge=charge, amount=amount_cents,
            metadata={"ticket_id": ticket_id},
            idempotency_key=idempotency_key,
        )
        return refund.id
