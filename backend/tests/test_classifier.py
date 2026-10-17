"""Unit: the deterministic classifier and amount extraction."""
from app.classifier import classify, extract_amount_cents


def test_refund_signals_win():
    cat, conf = classify("Charged twice this month\nI was charged twice, refund $49.00 please")
    assert cat == "refund_request"
    assert conf >= 0.85


def test_billing_inquiry():
    cat, _ = classify("Invoice copy needed\nCan you resend the invoice PDF for accounting?")
    assert cat == "billing_inquiry"


def test_bug_report():
    cat, _ = classify("500 error\nSaving any dashboard returns a 500 error, it fails every time")
    assert cat == "bug_report"


def test_account_issue():
    cat, _ = classify("Locked out\nI lost my phone with 2FA and can't log in")
    assert cat == "account_issue"


def test_how_to():
    cat, _ = classify("Export?\nHow do I export all our workspace data as JSON?")
    assert cat == "how_to"


def test_vague_message_stays_under_auto_threshold():
    from app.config import get_settings

    cat, conf = classify("hello\nhi")
    assert conf < get_settings().auto_resolve_threshold


def test_amount_extraction():
    assert extract_amount_cents("charged $49.00 yesterday") == 4900
    assert extract_amount_cents("paid $129 for the annual plan") == 12900
    assert extract_amount_cents("no money mentioned") is None
