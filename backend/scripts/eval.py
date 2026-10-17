"""Golden-set eval: measures the pipeline end to end (classify -> retrieve -> draft ->
route) on hand-written tickets with known answers. Reports per-metric accuracy and
exits non-zero below threshold, so CI fails loudly on a regression. Runs on the stub
LLM by default; set LLM_PROVIDER=openai to eval the real model with the same harness."""
import json
import os
import sys
import tempfile

import pgserver

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

THRESHOLDS = {"category": 0.85, "route": 0.85, "grounded": 1.0, "citation": 0.80}


def main() -> int:
    if "--ci" in sys.argv:
        sys.argv.remove("--ci")  # accepted for CI readability; behavior is env-driven
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = pgserver.get_server(
            tempfile.mkdtemp(prefix="resolvedesk-eval-pg")).get_uri().replace(
                "postgresql://", "postgresql+psycopg2://")
    from app import db
    from app.adapters import get_llm
    from app.agent import process_ticket
    from app.ingest import ingest_ticket
    from app.models import Draft
    from app.seed import seed_policy_docs

    db.init()
    db.drop_all()
    db.create_all()
    session = db.session()
    seed_policy_docs(session)
    llm = get_llm()

    golden = json.load(open(os.path.join(os.path.dirname(__file__), "..", "evals",
                                         "golden.json")))
    results = []
    for i, g in enumerate(golden):
        ticket, _ = ingest_ticket(session, {
            "external_id": f"eval-{i}", "subject": g["subject"], "body": g["body"],
            "customer_email": g["customer_email"]})
        draft = process_ticket(session, ticket, llm)
        session.commit()
        route = "human"
        if ticket.status == "auto_resolved":
            route = "auto"
        grounded = (draft.grounded_ok if draft else False) if g["expect_cite_any"] else None
        cited = [c["doc_slug"] for d in ([draft] if draft else []) for c in d.citations]
        cite_ok = None
        if g["expect_cite_any"] and draft:
            cite_ok = any(s in cited for s in g["expect_cite_any"])
        results.append({
            "subject": g["subject"],
            "category_ok": ticket.category == g["expect_category"],
            "route_ok": route == g["expect_route"],
            "grounded_ok": grounded,
            "cite_ok": cite_ok,
        })

    def rate(key, rows):
        rows = [r for r in rows if r.get(key) is not None]
        return sum(1 for r in rows if r[key]) / max(1, len(rows)), len(rows)

    cat, n = rate("category_ok", results)
    rte, _ = rate("route_ok", results)
    gr, gn = rate("grounded_ok", results)
    ci, cn = rate("cite_ok", results)
    print(f"model: {llm.name}   tickets: {n}")
    print(f"classification accuracy : {cat:.0%}  (threshold {THRESHOLDS['category']:.0%})")
    print(f"routing accuracy        : {rte:.0%}  (threshold {THRESHOLDS['route']:.0%})")
    print(f"grounded drafts         : {gr:.0%} of {gn}  (threshold {THRESHOLDS['grounded']:.0%})")
    print(f"citation match          : {ci:.0%} of {cn}  (threshold {THRESHOLDS['citation']:.0%})")
    failures = [r["subject"] for r in results
                if not r["category_ok"] or not r["route_ok"]
                or r["grounded_ok"] is False or r["cite_ok"] is False]
    if failures:
        print("failures:", ", ".join(failures))
    ok = (cat >= THRESHOLDS["category"] and rte >= THRESHOLDS["route"]
          and gr >= THRESHOLDS["grounded"] and ci >= THRESHOLDS["citation"])
    print("EVAL", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
