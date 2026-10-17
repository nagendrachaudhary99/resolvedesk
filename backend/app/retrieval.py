"""Policy retrieval over Postgres full-text search (tsvector + ts_rank + ts_headline).
Chosen over a vector DB for the MVP: zero extra infrastructure, deterministic in CI,
and the citation quotes come straight from ts_headline so groundedness is checkable.
The pgvector upgrade path is documented in DESIGN.md."""
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import PolicyDoc


def _fts(session: Session, tsquery_sql: str, value: str, k: int) -> list:
    return session.execute(
        text(
            f"""
            SELECT id, slug, title, body,
                   ts_rank(setweight(to_tsvector('english', title), 'A') ||
                           setweight(to_tsvector('english', body), 'D'),
                           {tsquery_sql}) AS rank,
                   ts_headline('english', body, {tsquery_sql},
                               'MaxWords=40, MinWords=15, StartSel=<mark>, StopSel=</mark>, MaxFragments=1') AS span
            FROM policy_docs
            WHERE setweight(to_tsvector('english', title), 'A') ||
                  setweight(to_tsvector('english', body), 'D') @@ {tsquery_sql}
            ORDER BY rank DESC
            LIMIT :k
            """
        ),
        {"q": value, "k": k},
    ).fetchall()


def retrieve(session: Session, query: str, k: int = 3) -> list[dict]:
    """Strict AND match first (plainto_tsquery); if recall is thin, relax to a ranked
    OR over distinctive tokens. Both stages are real Postgres FTS ranked by ts_rank."""
    rows = list(_fts(session, "plainto_tsquery('english', :q)", query, k))
    if len(rows) < k:
        tokens = list(dict.fromkeys(w.lower() for w in re.findall(r"[A-Za-z]{4,}", query)))[:8]
        if tokens:
            or_q = " | ".join(tokens)
            seen = {r.id for r in rows}
            extra = [r for r in _fts(session, "to_tsquery('english', :q)", or_q, k)
                     if r.id not in seen]
            rows += extra[: k - len(rows)]

    if not rows:
        # Last-resort fallback: substring match on the longest distinctive word so the
        # pipeline still grounds instead of answering from nothing.
        words = [w.strip(".,?!$").lower() for w in query.split() if len(w) > 4]
        if words:
            like_rows = (
                session.query(PolicyDoc)
                .filter(PolicyDoc.body.ilike(f"%{max(words, key=len)}%"))
                .limit(k)
                .all()
            )
            return [
                {"id": d.id, "slug": d.slug, "title": d.title, "body": d.body,
                 "rank": 0.01, "span": d.body[:200]}
                for d in like_rows
            ]
        return []

    return [
        {"id": r.id, "slug": r.slug, "title": r.title, "body": r.body,
         "rank": float(r.rank), "span": r.span}
        for r in rows[:k]
    ]


def verify_citation(doc_body: str, quote: str) -> bool:
    """A citation is grounded only if its quote is a verbatim span of the cited doc.
    Enforced at draft-write time: unverifiable citations are dropped, not trusted."""
    norm = lambda s: " ".join(s.split()).lower()
    return bool(quote) and norm(quote) in norm(doc_body)
