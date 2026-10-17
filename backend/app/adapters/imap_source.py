"""Real IMAP intake adapter. Enabled when RD_IMAP_HOST is set. Polls UNSEEN mail and
maps Message-ID -> ticket external_id, which is a genuine idempotency anchor: IMAP
re-delivery of the same message can never create a second ticket."""
import email
import imaplib
import os

from ..ports import TicketSource


class ImapTicketSource:
    name = "imap"

    def __init__(self, host: str, user: str, password: str, mailbox: str = "INBOX") -> None:
        self.host, self.user, self.password, self.mailbox = host, user, password, mailbox

    @classmethod
    def from_env(cls) -> "ImapTicketSource":
        return cls(
            host=os.environ["RD_IMAP_HOST"],
            user=os.environ["RD_IMAP_USER"],
            password=os.environ["RD_IMAP_PASSWORD"],
            mailbox=os.environ.get("RD_IMAP_MAILBOX", "INBOX"),
        )

    def poll(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        with imaplib.IMAP4_SSL(self.host) as conn:
            conn.login(self.user, self.password)
            conn.select(self.mailbox)
            _, data = conn.search(None, "UNSEEN")
            for num in (data[0] or b"").split():
                _, msg_data = conn.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", "replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", "replace")
                message_id = (msg.get("Message-ID") or f"imap-{num.decode()}").strip()
                out.append({
                    "external_id": message_id,
                    "subject": (msg.get("Subject") or "(no subject)").strip(),
                    "body": body.strip()[:10000],
                    "customer_email": (msg.get("From") or "unknown@unknown").strip(),
                })
        return out
