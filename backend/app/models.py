"""Schema. Postgres features used on purpose: SKIP LOCKED (outbox), tsvector (retrieval),
jsonb (payloads), and unique constraints that carry the idempotency story."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # external_id is the idempotency anchor for ingest: the same delivery retried
    # by the producer maps to one row.
    external_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    # new -> drafted -> auto_resolved | pending_approval -> resolved | needs_review | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    category: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 onupdate=utcnow)

    drafts: Mapped[list["Draft"]] = relationship(back_populates="ticket")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="ticket")


class PolicyDoc(Base):
    __tablename__ = "policy_docs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False)
    # citations: [{"doc_slug": ..., "doc_title": ..., "quote": ...}] - quotes are verbatim
    # spans of the cited doc, checked at write time (groundedness is enforced, not hoped for).
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    retrieved_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    grounded_ok: Mapped[bool] = mapped_column(nullable=False, default=False)
    llm_model: Mapped[str] = mapped_column(String(64), nullable=False)
    route: Mapped[str] = mapped_column(String(32), nullable=False)  # auto | human
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="drafts")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)  # send_reply | refund
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="approvals")


class OutboxEvent(Base):
    """Transactional outbox: side effects are committed as rows in the same transaction
    as the state change that caused them, then executed by the worker. Retries are safe
    because every event carries an idempotency key the executor enforces."""
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # send_reply | refund
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_outbox_pending", "status", "created_at"),
    )


class PaymentLedger(Base):
    """The fake payment provider's own ledger. It enforces idempotency the way a real
    provider does (unique idempotency key), which is what makes crash-safe refunds real."""
    __tablename__ = "payments_ledger"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="charged")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)  # agent | human | system
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 index=True)

    __table_args__ = (
        Index("ix_audit_ticket", "ticket_id", "created_at"),
        UniqueConstraint("ticket_id", "action", name="uq_audit_ticket_action"),
    )
