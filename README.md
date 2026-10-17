# ResolveDesk

[![ci](https://github.com/nagendrachaudhary99/resolvedesk/actions/workflows/ci.yml/badge.svg)](https://github.com/nagendrachaudhary99/resolvedesk/actions/workflows/ci.yml)

An AI support-resolution platform that actually closes tickets: it reads incoming
support email, grounds every reply in your policy docs with verified citations,
auto-resolves the safe ones, and puts anything involving money or account changes
in front of a human - with every action durable, idempotent, and auditable.

Built with FastAPI, PostgreSQL, and React. The pipeline core never knows which
adapters are live: seeded/dev adapters by default, real IMAP email intake, real
SMTP sending, real Stripe refunds, and real OpenAI generation when you provide
keys. Same code path either way.

## Why it exists

Most AI-support demos are chatbot wrappers. The hard part of agents in production
is everything around the model: what happens when the worker crashes mid-refund,
when the same webhook fires twice, when the model returns garbage, when a citation
is hallucinated. ResolveDesk is built around those questions:

- **Transactional outbox** - side effects are committed as rows in the same
  transaction as the decision that caused them. Crashes leave work, not damage.
- **Idempotency everywhere** - ingest dedupes on `external_id`, the outbox dedupes
  on idempotency keys, and the payment layer enforces them the way Stripe does.
  Retried anything converges to exactly one effect.
- **Enforced grounding** - a citation ships only if its quote is a verbatim span
  of the cited policy doc. Unverifiable citations are dropped at write time.
- **Risk-based routing** - informational tickets auto-resolve only above a
  confidence threshold AND with verified citations. Money and account changes
  never auto-resolve. No exceptions for confident models.
- **Real evals and load tests** - golden-set classification/routing/groundedness
  evals and a load harness run in CI, not just on a laptop.

## Architecture

```
                 ┌──────────────┐   webhook/IMAP/seed   ┌─────────────┐
                 │ TicketSource │ ───────────────────▶  │   Ingest    │  idempotent
                 └──────────────┘                       │ (external_id)│
                                                        └──────┬──────┘
                                                               ▼
   ┌─────────────────── one transaction ──────────────────────────────┐
   │  classify (LLM)  ▶  retrieve (Postgres FTS)  ▶  draft (LLM)      │
   │        │                                      ▶ verify citations │
   │        ▼                                      ▶ risk gate        │
   │   audit rows        draft row        approvals │ outbox events   │
   └────────────────────────────────────────────────┬────────────────┘
                                                     ▼
                                        ┌──────────────────────┐
                                        │  Worker (SKIP LOCKED) │  retry-safe
                                        │  send_reply / refund  │  idempotent
                                        └──────────┬───────────┘
                                                   ▼
                              ReplyChannel (console | SMTP) · Payments (fake | Stripe)
```

The console (React) shows the inbox with drafts and citations, the human approval
queue, and the append-only audit trail attributing every action to agent, human,
or system.

## Quickstart

With Docker (everything, one command):

```bash
cp .env.example .env
docker compose up --build
# console: http://localhost:5173   api: http://localhost:8000/docs
```

Local dev (no Docker): start Postgres, then

```bash
cd backend && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg2://resolvedesk:resolvedesk@localhost:5432/resolvedesk
uvicorn app.main:app --reload          # API on :8000
python -m app.worker                   # polls tickets + drains outbox
cd frontend && npm install && npm run dev   # console on :5173
```

Send a ticket through the full pipeline:

```bash
curl -X POST localhost:8000/tickets -H 'X-API-Token: dev-token' \
  -H 'Content-Type: application/json' -d '{
    "subject": "Charged twice",
    "body": "I was charged twice, two charges of $49.00. Please refund one.",
    "customer_email": "ava@acme.io"}'
# -> routed to a human (money never auto-resolves); approve it in the console,
#    the worker executes the refund exactly once, the audit trail shows all of it.
```

## Verification

```bash
cd backend
python -m pytest tests/ -q        # 30 tests: unit, integration, failure injection
python scripts/eval.py            # golden-set eval (fails CI below thresholds)
python scripts/load_test.py -n 500
```

Current numbers (embedded Postgres, single worker, this repo's CI hardware class):

| Metric | Result |
| --- | --- |
| Tests | 30 passing (unit, integration vs real Postgres, failure injection) |
| Classification accuracy (golden set, 24 tickets) | 100% |
| Routing accuracy | 100% |
| Grounded drafts (verified citations) | 100% |
| Citation match on expected doc | 91% |
| Load: 500 tickets through the full pipeline | 61 tickets/s, p50 399ms, p95 577ms, 0 errors |
| Side-effect drain | ~95 effects/s, exactly-once verified under crash injection |

The failure-injection suite kills the worker after a refund commits but before the
outbox updates, delivers duplicate webhooks, feeds the pipeline a garbage and a
timing-out LLM, and exhausts the retry cap - and asserts the system converges
correctly in every case.

## What's real vs stubbed

Honesty table, because demos overclaim:

| Component | Default (key-free) | Real adapter (set env, same code path) |
| --- | --- | --- |
| Ticket intake | Seeded generator | **IMAP** polling (`RD_IMAP_*`) - real mailbox |
| Reply sending | Console log | **SMTP** (`RD_SMTP_*`) - real email |
| Refunds | Fake provider with a **real ledger and real idempotency semantics** | **Stripe** (`STRIPE_API_KEY`) - real refunds |
| LLM | Deterministic rules model | **OpenAI** (`LLM_PROVIDER=openai`, `OPENAI_API_KEY`) |
| Retrieval | Real Postgres FTS (tsvector/ts_rank) | pgvector semantic search (roadmap) |
| Auth | Single dev token | Real auth + multi-tenancy (roadmap) |
| Database, queue, outbox, audit, API, console, tests, evals, load | **Real.** No mocks in the core path. | - |

The fake payment provider is deliberate: its ledger enforces unique idempotency
keys exactly like Stripe's API, which is what makes the crash-recovery tests mean
something. It is not a mock that returns success - it is a second implementation
of the same contract.

## Layout

```
backend/app/
  ports.py            hexagonal interfaces: LLM, ReplyChannel, PaymentProvider, TicketSource
  adapters/           stub + real implementations, selected by env
  agent.py            classify -> retrieve -> draft -> verify -> risk gate -> route
  outbox.py           worker: SKIP LOCKED claim, idempotent handlers, retry cap
  ingest.py           idempotent front door (external_id dedupe)
  retrieval.py        Postgres FTS with title weighting + verbatim-span citations
  seed.py             policy docs + realistic ticket generator
backend/tests/        30 tests incl. failure injection
backend/evals/        hand-written golden set
backend/scripts/      eval.py, load_test.py
frontend/             React console: inbox, approvals, audit trail
DESIGN.md             architecture, tradeoffs, failure modes, scaling path
ROADMAP.md            what comes after the MVP
```

Design decisions and their alternatives are in [DESIGN.md](DESIGN.md).
Planned phases are in [ROADMAP.md](ROADMAP.md).
