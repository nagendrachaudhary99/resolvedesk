"""Engine and session management. One engine per process; sessions are request-scoped."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def init(database_url: str | None = None) -> None:
    """(Re)initialize the global engine. Tests call this with a fresh database URL."""
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    _engine = create_engine(url, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=True, expire_on_commit=False)


def engine():
    if _engine is None:
        init()
    return _engine


def session():
    if _SessionLocal is None:
        init()
    return _SessionLocal()


def create_all() -> None:
    # Import models so metadata is populated before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(engine())


def drop_all() -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine())
