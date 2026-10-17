"""HTTP API for the console and for external ticket intake (webhook-style).
Auth is a single dev token (X-API-Token) - deliberately minimal for the prototype;
the roadmap documents real auth."""
import logging
import os

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from . import db
from .adapters import get_llm
from .agent import audit, enqueue, process_ticket
from .config import get_settings
from .ingest import ingest_ticket
from .models import Approval, AuditEvent, Draft, OutboxEvent, Ticket
from .seed import seed_policy_docs

log = logging.getLogger("resolvedesk.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init(os.environ.get("DATABASE_URL") or None)
    db.create_all()
    seed_policy_docs(db.session())
    yield


app = FastAPI(title="ResolveDesk", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def get_db():
    s = db.session()
    try:
        yield s
    finally:
        s.close()


def require_token(x_api_token: str = Header(default="")) -> None:
    if x_api_token != get_settings().api_token:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Token")


class TicketIn(BaseModel):
    subject: str
    body: str
    customer_email: EmailStr
    external_id: str | None = None


class DecisionIn(BaseModel):
    decision: str  # approve | reject
    decided_by: str = "console-user"


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/tickets", status_code=201, dependencies=[Depends(require_token)])
def create_ticket(payload: TicketIn, session: Session = Depends(get_db)) -> dict:
    """Webhook-style intake. Idempotent on external_id; the pipeline runs inline so the
    response carries the full triage result. Side effects stay on the outbox worker."""
    raw = payload.model_dump()
    raw["external_id"] = raw["external_id"] or f"api-{payload.customer_email}-{hash(payload.subject + payload.body) & 0xffffffff:08x}"
    ticket, created = ingest_ticket(session, raw)
    if not created:
        return {"ticket_id": ticket.id, "duplicate": True, "status": ticket.status}
    draft = process_ticket(session, ticket, get_llm())
    session.commit()
    return {"ticket_id": ticket.id, "duplicate": False, "status": ticket.status,
            "category": ticket.category, "confidence": ticket.confidence,
            "route": draft.route if draft else None}


def _ticket_json(t: Ticket, session: Session, full: bool = False) -> dict:
    out = {"id": t.id, "subject": t.subject, "status": t.status, "category": t.category,
           "confidence": t.confidence, "customer_email": t.customer_email,
           "created_at": t.created_at.isoformat()}
    if full:
        out["body"] = t.body
        out["drafts"] = [
            {"id": d.id, "reply_text": d.reply_text, "citations": d.citations,
             "confidence": d.confidence, "grounded_ok": d.grounded_ok, "route": d.route,
             "llm_model": d.llm_model, "created_at": d.created_at.isoformat()}
            for d in session.query(Draft).filter(Draft.ticket_id == t.id)
            .order_by(Draft.created_at.desc()).all()
        ]
        out["approvals"] = [
            {"id": a.id, "action_type": a.action_type, "payload": a.payload,
             "status": a.status, "decided_by": a.decided_by}
            for a in session.query(Approval).filter(Approval.ticket_id == t.id).all()
        ]
    return out


@app.get("/tickets")
def list_tickets(status: str | None = None, limit: int = 100,
                 session: Session = Depends(get_db)) -> list[dict]:
    q = session.query(Ticket).order_by(Ticket.created_at.desc())
    if status:
        q = q.filter(Ticket.status == status)
    return [_ticket_json(t, session) for t in q.limit(limit).all()]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, session: Session = Depends(get_db)) -> dict:
    t = session.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(404, "ticket not found")
    return _ticket_json(t, session, full=True)


@app.get("/approvals")
def list_approvals(status: str = "pending", session: Session = Depends(get_db)) -> list[dict]:
    rows = (session.query(Approval, Ticket).join(Ticket, Approval.ticket_id == Ticket.id)
            .filter(Approval.status == status).order_by(Approval.created_at).all())
    return [{"id": a.id, "ticket_id": a.ticket_id, "action_type": a.action_type,
             "payload": a.payload, "status": a.status, "ticket_subject": t.subject,
             "customer_email": t.customer_email,
             "created_at": a.created_at.isoformat()} for a, t in rows]


@app.post("/approvals/{approval_id}/decision", dependencies=[Depends(require_token)])
def decide(approval_id: str, payload: DecisionIn,
           session: Session = Depends(get_db)) -> dict:
    """Human decision. Approving enqueues the side effect in the SAME transaction as the
    decision - an approval can never be recorded without its action becoming runnable."""
    a = session.get(Approval, approval_id)
    if not a:
        raise HTTPException(404, "approval not found")
    if a.status != "pending":
        raise HTTPException(409, f"approval already {a.status}")
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")

    a.status = "approved" if payload.decision == "approve" else "rejected"
    a.decided_by = payload.decided_by
    from datetime import datetime, timezone

    a.decided_at = datetime.now(timezone.utc)
    audit(session, a.ticket_id, "human", f"approval_{a.status}",
          {"action_type": a.action_type, "decided_by": payload.decided_by})
    if a.status == "approved":
        if a.action_type == "refund":
            enqueue(session, a.ticket_id, "refund",
                    {"amount_cents": a.payload["amount_cents"]})
        elif a.action_type == "send_reply":
            enqueue(session, a.ticket_id, "send_reply",
                    {"to": a.payload["to"], "subject": a.payload["subject"],
                     "body": a.payload["body"]})
    # If every approval for the ticket is decided and none enqueued, finalize status.
    remaining = session.query(Approval).filter(
        Approval.ticket_id == a.ticket_id, Approval.status == "pending").count()
    if remaining == 0 and a.status == "rejected":
        t = session.get(Ticket, a.ticket_id)
        others = session.query(Approval).filter(
            Approval.ticket_id == a.ticket_id, Approval.status == "approved").count()
        if t and others == 0:
            t.status = "needs_review"  # everything rejected: a human owns the next step
    session.commit()
    return {"approval_id": a.id, "status": a.status}


@app.get("/audit")
def list_audit(ticket_id: str | None = None, limit: int = 200,
               session: Session = Depends(get_db)) -> list[dict]:
    q = session.query(AuditEvent).order_by(AuditEvent.created_at.desc())
    if ticket_id:
        q = q.filter(AuditEvent.ticket_id == ticket_id)
    return [{"id": e.id, "ticket_id": e.ticket_id, "actor": e.actor, "action": e.action,
             "detail": e.detail, "created_at": e.created_at.isoformat()}
            for e in q.limit(limit).all()]


@app.get("/outbox")
def list_outbox(status: str | None = None, session: Session = Depends(get_db)) -> list[dict]:
    q = session.query(OutboxEvent).order_by(OutboxEvent.created_at.desc())
    if status:
        q = q.filter(OutboxEvent.status == status)
    return [{"id": e.id, "ticket_id": e.ticket_id, "event_type": e.event_type,
             "status": e.status, "attempts": e.attempts, "last_error": e.last_error,
             "idempotency_key": e.idempotency_key} for e in q.limit(100).all()]
