# ResolveDesk - Roadmap

The MVP (this repo) proves the trustworthy core. Phases after it, in order.

## M1 - Harden the real adapters (next)
- IMAP intake soak: run against a live mailbox for a week; add UIDVALIDITY
  handling and seen-state persistence across restarts.
- SMTP: delivery-status tracking and bounce handling into the audit trail.
- Stripe: full refund round-trip on test keys, webhook reconciliation
  (Stripe event -> audit row), replacing the single-charge prototype path.
- OpenAI: prompt regression suite using the existing golden set; cost/latency
  logging per ticket into audit detail.

## M2 - Auth and multi-tenancy
- Workspace model: every table gains workspace_id; policy docs, tickets, and
  approvals scope to it.
- Real auth: per-user accounts (session or OIDC), roles mapping to the existing
  actor attribution (agent/human/system already recorded).
- Console: workspace switcher, per-user decision attribution.

## M3 - Channels and scale
- Intake queue: move ingest behind a broker (or LISTEN/NOTIFY first) so the
  pipeline scales horizontally; keep the sync path for small deployments.
- Slack intake + reply adapter (same ports).
- Helpdesk import: Zendesk/Intercom historical import for eval corpora.
- Rate limiting and per-workspace quotas at the API edge.

## M4 - Smarter retrieval and routing
- pgvector embeddings next to FTS, hybrid ranking (retrieval interface is
  already isolated for this).
- LLM-judge as an additional risk-gate signal (never the only one).
- Eval expansion: per-category golden sets, adversarial citation set, drift
  monitoring on the routing accuracy metric.
- Auto-resolve threshold tuning per category from measured outcomes.

## Explicitly not planned
- Autonomous money movement without human approval. The gate is the product.
- A general agent framework. ResolveDesk does one workflow completely.
