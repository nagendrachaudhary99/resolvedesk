"""Unit/integration: FTS retrieval and groundedness verification."""
from app.retrieval import retrieve, verify_citation


def test_refund_query_finds_refund_policy(session):
    docs = retrieve(session, "I was charged twice and want a refund")
    assert docs, "expected retrieval hits"
    slugs = [d["slug"] for d in docs]
    assert "refund-policy" in slugs or "double-charge" in slugs


def test_sso_query_finds_sso_doc(session):
    docs = retrieve(session, "How do we enable SAML SSO with Okta?")
    assert any(d["slug"] == "sso-setup" for d in docs)


def test_citation_verification(session):
    from app.models import PolicyDoc

    doc = session.query(PolicyDoc).filter_by(slug="refund-policy").one()
    assert verify_citation(doc.body, "full refunds within 30 days")
    assert verify_citation(doc.body, "  Full   Refunds   within 30 days ")  # whitespace-normalized
    assert not verify_citation(doc.body, "lifetime refunds whenever you want")
    assert not verify_citation(doc.body, "")


def test_gibberish_query_falls_back_or_empty(session):
    docs = retrieve(session, "xyzzyqqq zzz")
    assert isinstance(docs, list)  # must not raise; empty is fine
