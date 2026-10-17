"""Seed data: policy docs for a fictional SaaS ("Northwind Metrics") and a realistic
ticket generator. This is the honest stand-in for a live mailbox; the IMAP adapter
connects the same pipeline to real email."""
from .models import PolicyDoc

POLICY_DOCS: list[dict[str, str]] = [
    {"slug": "refund-policy", "title": "Refund Policy",
     "body": "Northwind Metrics offers full refunds within 30 days of the original charge "
             "for any plan. After 30 days, refunds are prorated to whole unused months. "
             "Refunds return to the original payment method within 5-10 business days. "
             "Annual plans cancelled mid-term receive the prorated remainder. Double "
             "charges are always refunded in full regardless of timing."},
    {"slug": "double-charge", "title": "Duplicate Charges",
     "body": "If you see two identical charges, one is refunded in full within 5 business "
             "days. Banks sometimes show a pending authorization alongside the real charge; "
             "pending authorizations drop off on their own within 7 days and are not "
             "duplicate charges."},
    {"slug": "invoice-copies", "title": "Getting Invoice Copies",
     "body": "Every charge emails a PDF invoice automatically. Copies live under Settings "
             "> Billing > Invoices. If the email is missing, check spam, then download the "
             "PDF directly from the billing page. Invoices include VAT where applicable."},
    {"slug": "proration", "title": "Plan Changes and Proration",
     "body": "Upgrades take effect immediately and are prorated to the day. Downgrades take "
             "effect at the end of the current billing cycle and are not prorated. The "
             "prorated amount appears on the next invoice as a line item."},
    {"slug": "sales-tax", "title": "Sales Tax and VAT",
     "body": "US customers are charged sales tax based on their billing address state. EU "
             "customers are charged VAT at their country rate and can add a VAT ID under "
             "Settings > Billing to apply reverse charge on future invoices."},
    {"slug": "password-reset", "title": "Password Reset",
     "body": "Reset links come from noreply@northwind.example and expire after 60 minutes. "
             "If no email arrives within 5 minutes, check spam and confirm the address is "
             "the one on the account. SSO users do not have a password and must sign in "
             "through their identity provider."},
    {"slug": "sso-setup", "title": "SSO Configuration",
     "body": "SSO (SAML and Google Workspace) is available on Team and Enterprise plans. "
             "Admins enable it under Settings > Security. SAML requires the IdP metadata "
             "URL; attribute mapping for email is required. SCIM provisioning is "
             "Enterprise-only."},
    {"slug": "two-factor", "title": "Two-Factor Authentication",
     "body": "2FA supports TOTP authenticator apps. Recovery codes are shown once at setup "
             "and should be stored offline. If you lose both your device and recovery "
             "codes, an admin can reset 2FA after verifying your identity."},
    {"slug": "account-deletion", "title": "Deleting Your Account",
     "body": "Account deletion removes all data within 30 days and is irreversible. Export "
             "your data first. Deletion requests must come from the account owner; "
             "teammates cannot delete an owner's account."},
    {"slug": "data-export", "title": "Exporting Your Data",
     "body": "Full workspace exports (JSON and CSV) are under Settings > Data > Export. "
             "Exports over 1 GB are prepared asynchronously and emailed as a download link "
             "valid for 7 days. The API exposes the same data via the /export endpoint."},
    {"slug": "api-keys", "title": "API Keys",
     "body": "API keys are created under Settings > Developers. Keys are shown once at "
             "creation. Rotate keys every 90 days. A compromised key should be revoked "
             "immediately; revoking never affects other keys."},
    {"slug": "rate-limits", "title": "API Rate Limits",
     "body": "The API allows 600 requests per minute per key on Team plans and 300 on "
             "Starter. Exceeding the limit returns HTTP 429 with a Retry-After header. "
             "Back off exponentially; sustained overage is never a permanent ban."},
    {"slug": "webhook-retries", "title": "Webhook Delivery and Retries",
     "body": "Failed webhook deliveries retry 8 times over 24 hours with exponential "
             "backoff. After the final retry the endpoint is paused and can be re-enabled "
             "from Settings > Webhooks. Every delivery carries an X-Northwind-Event-Id "
             "header you should dedupe on."},
    {"slug": "sla-credits", "title": "Uptime SLA and Credits",
     "body": "Enterprise plans carry a 99.9% uptime SLA. Monthly uptime below that earns a "
             "service credit of 10% per 0.1% below target, up to 100% of the month. "
             "Credits must be requested within 30 days of the incident month."},
    {"slug": "trial-extension", "title": "Extending a Trial",
     "body": "Trials last 14 days. One extension of 7 days is available per workspace from "
             "Settings > Billing while the trial is active. Expired trials keep data "
             "read-only for 30 days before deletion."},
    {"slug": "downgrade-data", "title": "What Happens on Downgrade",
     "body": "Downgrading never deletes data. Features above the new plan become "
             "read-only: dashboards stay visible, alerts pause, SSO sign-in is disabled "
             "but password sign-in keeps working."},
    {"slug": "billing-address", "title": "Changing Billing Details",
     "body": "Billing address, company name, and tax IDs can be updated under Settings > "
             "Billing and apply to future invoices. Already-issued invoices cannot be "
             "edited; a corrected copy can be reissued on request."},
    {"slug": "status-page", "title": "Checking Service Status",
     "body": "status.northwind.example shows live component status and 90 days of "
             "incident history. You can subscribe to incident updates by email or RSS. "
             "Errors that match an active incident need no ticket."},
    {"slug": "error-500", "title": "Troubleshooting 500 Errors",
     "body": "A 500 error with a request ID should be reported with that ID. First check "
             "status.northwind.example. Retrying with the same Idempotency-Key header is "
             "always safe; the API guarantees at-most-once effects per key."},
    {"slug": "session-timeout", "title": "Session Timeouts",
     "body": "Sessions expire after 14 days of inactivity or immediately on password "
             "change. Admins can set shorter org-wide timeouts under Settings > Security. "
             "Being logged out is expected behavior, not a bug, after 14 idle days."},
    {"slug": "import-csv", "title": "Importing Data from CSV",
     "body": "CSV import is under Settings > Data > Import. Files up to 50 MB are "
             "processed synchronously; larger files queue and email when done. Column "
             "mapping is saved per workspace after the first import."},
    {"slug": "alert-rules", "title": "Configuring Alert Rules",
     "body": "Alerts fire when a metric crosses a threshold for a sustained window. The "
             "default window is 5 minutes to avoid flapping. Alert channels: email, "
             "Slack, and webhooks. Test an alert with the Send Test button before "
             "relying on it."},
    {"slug": "dashboard-sharing", "title": "Sharing Dashboards",
     "body": "Dashboards can be shared with teammates (edit or view) or as a public "
             "read-only link. Public links can be revoked at any time and expire "
             "automatically after 90 days of no views."},
    {"slug": "keyboard-shortcuts", "title": "Keyboard Shortcuts",
     "body": "Press ? anywhere to see shortcuts. g d goes to dashboards, g a to alerts, "
             "/ focuses search, and c creates a new dashboard. Shortcuts can be disabled "
             "in Settings > Preferences."},
    {"slug": "mobile-app", "title": "Mobile Apps",
     "body": "iOS and Android apps support viewing dashboards and receiving alerts. "
             "Editing dashboards requires the web app. Push notifications mirror your "
             "email alert subscriptions by default."},
]

_FIRST = ["Ava", "Liam", "Maya", "Noah", "Sofia", "Ethan", "Priya", "Marco", "June", "Omar",
          "Elena", "Dan", "Kai", "Ruth", "Victor", "Nina", "Sam", "Tara", "Leo", "Iris"]
_DOMAINS = ["acme.io", "globex.com", "initech.dev", "umbrella.co", "starklabs.io",
            "waynecorp.com", "wonka.io", "cyberdyne.dev", "aperture.co", "tyrell.io"]

# (category-intent, subject template, body template) - amount slots where relevant.
_TEMPLATES = [
    ("refund", "Charged twice this month",
     "Hi, I was charged twice for my Team plan - two charges of $AMT on the 3rd. "
     "Please refund the duplicate. Thanks, NAME"),
    ("refund", "Refund request",
     "Hello, I cancelled last week but was still charged $AMT yesterday. I want a "
     "refund for that charge. - NAME"),
    ("refund", "Want my money back",
     "Your product didn't work for us. We paid $AMT two weeks ago and want a full "
     "refund. NAME"),
    ("refund", "Refund for annual plan",
     "We upgraded to annual 10 days ago for $AMT and realized we don't need it. "
     "Can we get a refund? Thanks, NAME"),
    ("billing", "Invoice copy needed",
     "Hi, I never received the invoice PDF for this month's charge of $AMT. Can you "
     "resend it? Our accounting needs it. NAME"),
    ("billing", "Question about proration",
     "If I upgrade from Starter to Team mid-cycle, how is the prorated amount "
     "calculated? Current bill is $AMT/mo. NAME"),
    ("billing", "VAT on invoice",
     "We're based in Germany and were charged VAT even though we have a VAT ID. "
     "How do I add it so future invoices use reverse charge? - NAME"),
    ("billing", "What is this charge?",
     "There's a $AMT charge from Northwind on our card and I don't recognize it. "
     "What is it for? NAME"),
    ("bug", "500 error when saving dashboard",
     "Since this morning, saving any dashboard returns a 500 error with request ID "
     "req_9f2. Is this a known issue? NAME"),
    ("bug", "App crashes on export",
     "The web app crashes every time I export a large CSV. Tried Chrome and "
     "Firefox, same thing. This is blocking our month-end reporting. NAME"),
    ("bug", "Alerts not firing",
     "My alert rule for error rate over 5% didn't fire last night even though the "
     "metric was at 12% for an hour. Is something broken? NAME"),
    ("account", "Locked out of my account",
     "I lost my phone with my authenticator app and don't have recovery codes. "
     "I'm the workspace owner. How do I get back in? NAME"),
    ("account", "Password reset email never arrives",
     "I've requested a password reset 4 times in the last hour and no email shows "
     "up. Not in spam either. Help! NAME"),
    ("account", "Delete my account",
     "Please delete my account and all associated data. I understand this is "
     "permanent. - NAME"),
    ("account", "SSO setup help",
     "We're on the Team plan and want to enable SAML SSO with Okta. What do you "
     "need from us? NAME"),
    ("howto", "How do I export my data?",
     "Hi, what's the best way to export all our workspace data as JSON before our "
     "renewal? NAME"),
    ("howto", "Webhook retries",
     "Our webhook endpoint was down for 2 days. Will you retry the failed "
     "deliveries, and how do I dedupe them? Thanks, NAME"),
    ("howto", "Where do I create an API key?",
     "I need an API key for our data pipeline. Where do I create one and can I "
     "rotate it without downtime? NAME"),
    ("howto", "Share a dashboard publicly",
     "Is there a way to share a dashboard with a client who doesn't have an "
     "account? Ideally a read-only link. NAME"),
    ("howto", "Keyboard shortcut for search?",
     "Quick one - is there a keyboard shortcut to jump to search? I live in this "
     "app. NAME"),
]


def generate_tickets(count: int, offset: int = 0) -> list[dict[str, str]]:
    out = []
    for i in range(count):
        n = offset + i
        _, subject, body = _TEMPLATES[n % len(_TEMPLATES)]
        name = _FIRST[n % len(_FIRST)]
        domain = _DOMAINS[(n * 7) % len(_DOMAINS)]
        amount = [2400, 4900, 9900, 14900, 2900, 7900][n % 6]
        out.append({
            "external_id": f"seed-{n:05d}@generated",
            "subject": subject,
            "body": body.replace("NAME", name).replace("AMT", f"{amount/100:.2f}"),
            "customer_email": f"{name.lower()}@{domain}",
        })
    return out


def seed_policy_docs(session) -> int:
    from .models import PolicyDoc

    existing = session.query(PolicyDoc).count()
    if existing:
        return 0
    for d in POLICY_DOCS:
        session.add(PolicyDoc(slug=d["slug"], title=d["title"], body=d["body"]))
    session.commit()
    return len(POLICY_DOCS)
