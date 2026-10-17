"""Adapter selection. Env config decides which implementation each port gets;
the pipeline core imports the ports, never the concrete adapters."""
from ..config import get_settings
from ..ports import LLMClient, PaymentProvider, ReplyChannel, TicketSource


def get_llm() -> LLMClient:
    s = get_settings()
    if s.llm_provider == "openai" and s.openai_api_key:
        from .openai_llm import OpenAILLM

        return OpenAILLM(api_key=s.openai_api_key, model=s.openai_model)
    from .stub_llm import StubLLM

    return StubLLM()


def get_reply_channel() -> ReplyChannel:
    import os

    if os.environ.get("RD_SMTP_HOST"):
        from .smtp_reply import SMTPReplyChannel

        return SMTPReplyChannel.from_env()
    from .console_reply import ConsoleReplyChannel

    return ConsoleReplyChannel()


def get_payment_provider() -> PaymentProvider:
    import os

    if os.environ.get("STRIPE_API_KEY"):
        from .stripe_payments import StripePaymentProvider

        return StripePaymentProvider()
    from .fake_payments import FakePaymentProvider

    return FakePaymentProvider()


def get_ticket_source() -> TicketSource:
    import os

    if os.environ.get("RD_IMAP_HOST"):
        from .imap_source import ImapTicketSource

        return ImapTicketSource.from_env()
    from .seed_source import SeededTicketSource

    return SeededTicketSource()
