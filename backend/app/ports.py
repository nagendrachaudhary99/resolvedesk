"""Ports (hexagonal architecture). Every external system sits behind one of these
interfaces, so the pipeline core never knows whether it is talking to the seeded
dev adapters or the real IMAP/SMTP/Stripe/OpenAI ones. Adapters are selected by
env config at startup - see app/adapters/__init__.py."""
from typing import Any, Protocol


class LLMClient(Protocol):
    """Structured-completion client. Returns a dict conforming to the task's schema
    or raises LLMError. Implementations: StubLLM (deterministic, default),
    OpenAILLM (real, when OPENAI_API_KEY is set)."""
    name: str

    def complete_json(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class LLMError(Exception):
    pass


class ReplyChannel(Protocol):
    """Where a resolved reply actually goes. Console (dev default) or SMTP (real email)."""
    name: str

    def send(self, to_email: str, subject: str, body: str, idempotency_key: str) -> str:
        """Returns a provider message id. Must be idempotent on idempotency_key."""
        ...


class PaymentProvider(Protocol):
    """Refund execution. Fake ledger (default) or real Stripe (when STRIPE_API_KEY is set).
    Both enforce idempotency keys the way Stripe does."""
    name: str

    def refund(self, *, idempotency_key: str, ticket_id: str, amount_cents: int) -> str:
        """Returns a provider refund id. Must never double-charge on retry."""
        ...


class TicketSource(Protocol):
    """Inbound ticket stream. Seeded generator (default) or real IMAP inbox."""
    name: str

    def poll(self) -> list[dict[str, str]]:
        """Returns new raw tickets: {external_id, subject, body, customer_email}."""
        ...
