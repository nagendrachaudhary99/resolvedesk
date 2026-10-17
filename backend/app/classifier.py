"""Deterministic ticket classifier. This is the rules engine the StubLLM wraps, and it
is also the fallback when the real LLM is unavailable or returns garbage. Rule-based
classification on purpose: it is testable, and the golden-set eval measures the whole
pipeline rather than a model we don't control in CI."""
import re

CATEGORIES = ["refund_request", "billing_inquiry", "bug_report", "account_issue", "how_to"]

_RULES: list[tuple[str, list[str], float]] = [
    ("refund_request", [r"\brefund\b", r"\bchargeback\b", r"\bmoney back\b", r"\bcancel and refund\b", r"\bget (a )?refund\b",
                        r"\bdouble[- ]?charged\b", r"\bcharged twice\b"], 0.90),
    ("billing_inquiry", [r"\binvoice\b", r"\breceipt\b", r"\bbilling\b", r"\bprorat", r"\bwhat (was|is) this charge\b",
                         r"\bplan (price|cost)\b", r"\bvat\b", r"\btax\b"], 0.85),
    ("bug_report", [r"\berror\b", r"\bcrash", r"\bbug\b", r"\bbroken\b", r"\b500\b", r"\bstack ?trace\b",
                    r"\bnot (saving|working|loading)\b", r"\bfails?\b"], 0.82),
    ("account_issue", [r"\bpassword\b", r"\blog ?in\b", r"\bsign ?in\b", r"\bsso\b", r"\b2fa\b", r"\bmfa\b",
                       r"\blocked out\b", r"\bdelete (my |our |the )?account\b", r"\bchange (my )?email\b"], 0.85),
    ("how_to", [r"\bhow (do|can|to)\b", r"\bwhere (do|can)\b", r"\bis there a way\b", r"\bguide\b",
                r"\btutorial\b", r"\bexport\b", r"\bintegrat", r"\bapi key\b", r"\bwebhook\b"], 0.80),
]

_AMOUNT_RE = re.compile(r"\$\s?(\d{1,6}(?:\.\d{2})?)")


def classify(text: str) -> tuple[str, float]:
    t = text.lower()
    best_cat, best_score = "how_to", 0.55  # weak default, stays under the auto threshold
    for cat, patterns, base in _RULES:
        hits = sum(1 for p in patterns if re.search(p, t))
        if hits:
            score = min(0.99, base + 0.03 * (hits - 1))
            if score > best_score:
                best_cat, best_score = cat, score
    return best_cat, round(best_score, 3)


def extract_amount_cents(text: str) -> int | None:
    """First dollar amount mentioned, in cents. Refund approvals carry this."""
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    return int(round(float(m.group(1)) * 100))
