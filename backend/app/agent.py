"""The pipeline: classify -> retrieve -> draft -> verify grounding -> risk gate -> route.
Everything up to the side effect commits in ONE transaction; side effects themselves are
outbox rows in that same transaction. A crash anywhere before commit leaves nothing;
a crash after leaves work the worker can safely finish."""
import logging

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Approval, AuditEvent, Draft, OutboxEvent, Ticket
from .ports import LLMClient, LLMError
from .retrieval import retrieve, verify_citation

log = logging.getLogger("resolvedesk.agent")

AUTO_ELIGIBLE = {"how_to", "billing_inquiry"}  # informational only, no money, no mutation
VALID_CATEGORIES = {"refund_request", "billing_inquiry", "bug_report", "account_issue", "how_to"}


def audit(session: Session, ticket_id: str, actor: str, action: str, detail: dict) -> None:
    exists = (
        session.query(AuditEvent)
        .filter(AuditEvent.ticket_id == ticket_id, AuditEvent.action == action)
        .one_or_none()
    )
    if not exists:
        session.add(AuditEvent(ticket_id=ticket_id, actor=actor, action=action, detail=detail))


def enqueue(session: Session, ticket_id: str, event_type: str, payload: dict) -> OutboxEvent:
    key = f"{ticket_id}:{event_type}"
    existing = (
        session.query(OutboxEvent).filter(OutboxEvent.idempotency_key == key).one_or_none()
    )
    if existing:
        return existing
    ev = OutboxEvent(ticket_id=ticket_id, event_type=event_type, payload=payload,
                     idempotency_key=key)
    session.add(ev)
    return ev


def process_ticket(session: Session, ticket: Ticket, llm: LLMClient) -> Draft | None:
    """Runs the full pipeline for one ticket inside the caller's transaction.
    Returns the Draft, or None when the ticket is parked in needs_review."""
    settings = get_settings()
    try:
        classification = llm.complete_json(
            "classify", {"subject": ticket.subject, "body": ticket.body})
        category = classification.get("category")
        if category not in VALID_CATEGORIES:
            raise LLMError(f"invalid category from llm: {category!r}")
        confidence = float(classification.get("confidence", 0.0))
        amount_cents = classification.get("amount_cents")
    except (LLMError, ValueError, TypeError, KeyError) as e:
        ticket.status = "needs_review"
        audit(session, ticket.id, "system", "llm_error", {"error": str(e)})
        log.warning("ticket %s -> needs_review (%s)", ticket.id, e)
        return None

    ticket.category = category
    ticket.confidence = confidence
    audit(session, ticket.id, "agent", "classified",
          {"category": category, "confidence": confidence, "model": llm.name})

    docs = retrieve(session, ticket.subject + "\n" + ticket.body, k=3)
    try:
        drafted = llm.complete_json("draft", {
            "category": category, "subject": ticket.subject, "body": ticket.body,
            "retrieved_docs": docs,
        })
        reply_text = str(drafted["reply_text"])
        raw_citations = drafted.get("citations") or []
    except (LLMError, ValueError, TypeError, KeyError) as e:
        ticket.status = "needs_review"
        audit(session, ticket.id, "system", "llm_error", {"error": str(e), "stage": "draft"})
        return None

    # Groundedness enforcement: keep only citations whose quote is verbatim in the doc.
    doc_by_slug = {d["slug"]: d for d in docs}
    citations = []
    for c in raw_citations:
        doc = doc_by_slug.get(c.get("doc_slug", ""))
        if doc and verify_citation(doc["body"], c.get("quote", "")):
            citations.append({"doc_slug": doc["slug"], "doc_title": doc["title"],
                              "quote": c["quote"]})
    grounded_ok = bool(citations)

    route = "human"
    if (category in AUTO_ELIGIBLE and grounded_ok
            and confidence >= get_settings().auto_resolve_threshold):
        route = "auto"
    # Money and account mutations NEVER auto-resolve, regardless of confidence.

    draft = Draft(ticket_id=ticket.id, reply_text=reply_text, citations=citations,
                  retrieved_doc_ids=[d["id"] for d in docs], confidence=confidence,
                  grounded_ok=grounded_ok, llm_model=llm.name, route=route)
    session.add(draft)
    audit(session, ticket.id, "agent", "drafted",
          {"grounded_ok": grounded_ok, "citations": len(citations), "route": route})

    if route == "auto":
        ticket.status = "auto_resolved"
        enqueue(session, ticket.id, "send_reply",
                {"to": ticket.customer_email, "subject": f"Re: {ticket.subject}",
                 "body": reply_text})
        audit(session, ticket.id, "agent", "routed_auto", {"confidence": confidence})
    else:
        ticket.status = "pending_approval"
        session.add(Approval(ticket_id=ticket.id, action_type="send_reply",
                             payload={"to": ticket.customer_email,
                                      "subject": f"Re: {ticket.subject}",
                                      "body": reply_text}))
        if category == "refund_request" and amount_cents:
            session.add(Approval(ticket_id=ticket.id, action_type="refund",
                                 payload={"amount_cents": int(amount_cents)}))
        audit(session, ticket.id, "agent", "routed_human",
              {"category": category, "confidence": confidence,
               "grounded_ok": grounded_ok})
    return draft
