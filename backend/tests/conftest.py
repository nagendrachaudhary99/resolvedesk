"""Test fixtures. Runs against a REAL Postgres - pgserver provides a throwaway
embedded cluster so integration tests exercise SKIP LOCKED, tsvector, and unique
constraints exactly as production does. No SQLite stand-ins."""
import os
import sys

import pgserver
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PG = None


def _pg_url() -> str:
    global _PG
    if _PG is None:
        _PG = pgserver.get_server("/tmp/resolvedesk-pgdata")
    return _PG.get_uri().replace("postgresql://", "postgresql+psycopg2://")


@pytest.fixture(scope="session", autouse=True)
def _database():
    url = _pg_url()
    os.environ["DATABASE_URL"] = url
    from app import db

    db.init(url)
    db.drop_all()
    db.create_all()
    yield
    db.drop_all()


@pytest.fixture()
def session():
    """Fresh-truncated database per test, with policy docs re-seeded."""
    from app import db
    from app.models import (Approval, AuditEvent, Draft, OutboxEvent, PaymentLedger,
                            PolicyDoc, Ticket)
    from app.seed import seed_policy_docs

    s = db.session()
    for model in (AuditEvent, OutboxEvent, Approval, Draft, PaymentLedger, Ticket, PolicyDoc):
        s.query(model).delete()
    s.commit()
    seed_policy_docs(s)
    yield s
    s.close()


@pytest.fixture()
def llm():
    from app.adapters.stub_llm import StubLLM

    return StubLLM()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app import db
    from app.main import app
    from app.models import (Approval, AuditEvent, Draft, OutboxEvent, PaymentLedger,
                            PolicyDoc, Ticket)
    from app.seed import seed_policy_docs

    s = db.session()
    for model in (AuditEvent, OutboxEvent, Approval, Draft, PaymentLedger, Ticket, PolicyDoc):
        s.query(model).delete()
    s.commit()
    seed_policy_docs(s)
    s.close()
    return TestClient(app)


AUTH = {"X-API-Token": "dev-token"}
