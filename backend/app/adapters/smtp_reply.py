"""Real email sending over SMTP (works with Gmail app passwords, Fastmail, etc.).
Enabled when RD_SMTP_HOST is set. Real sends are not retry-safe at the SMTP layer -
the outbox's idempotency key is what prevents duplicates on retry."""
import os
import smtplib
import ssl
from email.message import EmailMessage

from ..ports import ReplyChannel


class SMTPReplyChannel:
    name = "smtp"

    def __init__(self, host: str, port: int, user: str, password: str, from_addr: str) -> None:
        self.host, self.port, self.user, self.password, self.from_addr = (
            host, port, user, password, from_addr)

    @classmethod
    def from_env(cls) -> "SMTPReplyChannel":
        return cls(
            host=os.environ["RD_SMTP_HOST"],
            port=int(os.environ.get("RD_SMTP_PORT", "465")),
            user=os.environ["RD_SMTP_USER"],
            password=os.environ["RD_SMTP_PASSWORD"],
            from_addr=os.environ.get("RD_FROM_ADDR", os.environ["RD_SMTP_USER"]),
        )

    def send(self, to_email: str, subject: str, body: str, idempotency_key: str) -> str:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["X-Idempotency-Key"] = idempotency_key
        msg.set_content(body)
        with smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context()) as s:
            s.login(self.user, self.password)
            s.send_message(msg)
        return f"smtp-{idempotency_key[:16]}"
