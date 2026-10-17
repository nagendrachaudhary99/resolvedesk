"""API contract tests through the real HTTP layer."""
from app import db
from app.outbox import run_once


def test_auth_required(client):
    r = client.post("/tickets", json={"subject": "s", "body": "b",
                                      "customer_email": "a@b.co"})
    assert r.status_code == 401


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_full_auto_flow_over_http(client):
    r = client.post("/tickets", json={
        "subject": "How do I export data?",
        "body": "How do I export all our workspace data as JSON?",
        "customer_email": "leo@acme.io"}, headers={"X-API-Token": "dev-token"})
    assert r.status_code == 201
    body = r.json()
    assert body["route"] == "auto"
    tid = body["ticket_id"]

    detail = client.get(f"/tickets/{tid}").json()
    assert detail["status"] == "auto_resolved"
    assert detail["drafts"][0]["grounded_ok"] is True
    assert detail["drafts"][0]["citations"], "expected verified citations"

    run_once(db.session)  # drain outbox like the worker would
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["status"] == "resolved"

    audit = client.get(f"/audit?ticket_id={tid}").json()
    actions = {e["action"] for e in audit}
    assert {"ingested", "classified", "drafted", "routed_auto", "reply_sent"} <= actions


def test_full_human_flow_over_http(client):
    r = client.post("/tickets", json={
        "subject": "Refund $99.00",
        "body": "I want a refund of my $99.00 charge. Money back please.",
        "customer_email": "tara@acme.io"}, headers={"X-API-Token": "dev-token"})
    tid = r.json()["ticket_id"]
    assert r.json()["route"] == "human"

    approvals = [a for a in client.get("/approvals").json() if a["ticket_id"] == tid]
    assert sorted(a["action_type"] for a in approvals) == ["refund", "send_reply"]

    for a in approvals:
        resp = client.post(f"/approvals/{a['id']}/decision",
                           json={"decision": "approve", "decided_by": "dana"},
                           headers={"X-API-Token": "dev-token"})
        assert resp.status_code == 200

    run_once(db.session)
    run_once(db.session)
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["status"] == "resolved"
    audit = client.get(f"/audit?ticket_id={tid}").json()
    actions = {e["action"] for e in audit}
    assert {"refund_executed", "reply_sent", "approval_approved"} <= actions


def test_reject_all_sends_to_needs_review(client):
    r = client.post("/tickets", json={
        "subject": "Delete my account",
        "body": "Please delete my account and all data permanently.",
        "customer_email": "omar@acme.io"}, headers={"X-API-Token": "dev-token"})
    tid = r.json()["ticket_id"]
    for a in [a for a in client.get("/approvals").json() if a["ticket_id"] == tid]:
        client.post(f"/approvals/{a['id']}/decision",
                    json={"decision": "reject", "decided_by": "dana"},
                    headers={"X-API-Token": "dev-token"})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["status"] == "needs_review"
