"""Worker entry point: polls the ticket source (seeded or real IMAP) and drains the
outbox. `python -m app.worker --once` runs a single drain cycle (tests and load script
use this); the default is a loop."""
import argparse
import logging
import time

from . import db
from .adapters import get_llm, get_ticket_source
from .agent import process_ticket
from .config import get_settings
from .ingest import ingest_ticket
from .outbox import run_once
from .seed import seed_policy_docs

log = logging.getLogger("resolvedesk.worker")


def cycle(poll_source: bool = True) -> dict[str, int]:
    session = db.session()
    try:
        if poll_source:
            source = get_ticket_source()
            llm = get_llm()
            for raw in source.poll():
                ticket, created = ingest_ticket(session, raw)
                if created:
                    process_ticket(session, ticket, llm)
                    session.commit()
        return run_once(db.session)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-poll", action="store_true", help="skip source polling")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    db.init()
    db.create_all()
    seed_policy_docs(db.session())
    if args.once:
        print(cycle(poll_source=not args.no_poll))
        return
    settings = get_settings()
    log.info("worker loop starting (poll=%ss)", settings.worker_poll_seconds)
    while True:
        cycle(poll_source=False)
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
