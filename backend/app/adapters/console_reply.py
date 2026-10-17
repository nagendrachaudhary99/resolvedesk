"""Dev reply channel: records the send to stdout and returns a synthetic message id.
Idempotent by construction in the outbox (the worker dedupes before calling this)."""
import json
import logging

from ..ports import ReplyChannel

log = logging.getLogger("resolvedesk.reply")


class ConsoleReplyChannel:
    name = "console"

    def send(self, to_email: str, subject: str, body: str, idempotency_key: str) -> str:
        log.info("REPLY to=%s subject=%r key=%s\n%s", to_email, subject, idempotency_key, body)
        print(json.dumps({"sent_to": to_email, "subject": subject,
                          "idempotency_key": idempotency_key}))
        return f"console-{idempotency_key[:16]}"
