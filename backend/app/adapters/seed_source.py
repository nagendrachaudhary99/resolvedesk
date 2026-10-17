"""Seeded ticket source: the default inbound stream. Honest stand-in for a real
mailbox - the IMAP adapter is the live one."""
from ..ports import TicketSource
from ..seed import generate_tickets


class SeededTicketSource:
    name = "seeded"

    def __init__(self, batch: int = 5) -> None:
        self.batch = batch
        self._offset = 0

    def poll(self) -> list[dict[str, str]]:
        batch = generate_tickets(count=self.batch, offset=self._offset)
        self._offset += self.batch
        return batch
