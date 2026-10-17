# ResolveDesk - Design

## Problem

Support teams drown in repetitive tickets. AI can draft answers, but production
support automation fails on everything around the model: duplicate deliveries,
crashes between decision and side effect, hallucinated policy claims, and money
moving without a human signing off. The design question is not "can an LLM answer
a ticket" - it is "can the system around it be trusted with one."

**Solved means:** a ticket enters once, gets a grounded answer, and the safe ones
close themselves while the risky ones reach a human with everything prepared -
and no crash, retry, or duplicate anywhere in the system can cause a double
refund, a lost ticket, or an unattributed action.

## Actors and roles

| Role | Who | Can do |
| --- | --- | --- |
| Agent | The pipeline (LLM + rules) | Classify, retrieve, draft, route. Never moves money or mutates accounts. |
| Human approver | Support teammate via console | Approve/reject prepared actions. Their decision is attributed and audited. |
| System | Worker + outbox | Execute approved/auto side effects exactly once. Owns retries. |
| Auditor | Anyone reading the trail | Reconstruct who did what, when, and why from append-only audit rows. |

## Non-goals (MVP)

Multi-tenancy, real auth, multi-channel intake beyond one mailbox, agent
tool-use beyond the two prepared actions. Each is a deliberate cut, listed in
ROADMAP.md with the reason it is safe to add later.

## Architecture

Hexagonal (ports & adapters). The pipeline core (`agent.py`, `outbox.py`,
`ingest.py`, `retrieval.py`) depends only on the port interfaces in `ports.py`.
Every external system is an adapter selected by env config at startup:

| Port | Default adapter | Real adapter |
| --- | --- | --- |
| `TicketSource` | Seeded generator | IMAP (`imap_source.py`) - Message-ID is the ingest dedupe anchor |
| `ReplyChannel` | Console log | SMTP (`smtp_reply.py`) |
| `PaymentProvider` | Fake ledger (`fake_payments.py`) | Stripe SDK (`stripe_payments.py`) |
| `LLMClient` | Deterministic rules (`stub_llm.py`) | OpenAI JSON mode (`openai_llm.py`) |

The default set runs the entire system with zero keys and zero network; tests
and CI exercise the same code path the real adapters use.

### Data flow

1. **Ingest** (`ingest.py`): `external_id` is unique; a retried webhook or
   re-polled IMAP message returns the existing ticket. Exactly one row per
   delivery identity.
2. **Pipeline** (`agent.py`): classify -> retrieve -> draft -> verify -> route,
   all inside ONE transaction with the resulting draft row, approval rows,
   outbox rows, and audit rows. A crash mid-pipeline leaves nothing; a success
   leaves everything atomically.
3. **Risk gate**: auto-resolve requires (a) informational category
   (`how_to`, `billing_inquiry`), (b) confidence >= threshold, (c) at least one
   verified citation. Money and account mutations route to a human regardless
   of confidence.
4. **Outbox** (`outbox.py`): the worker claims events with
   `SELECT ... FOR UPDATE SKIP LOCKED`, executes the handler, records outcome.
   Handlers are idempotent; retries converge to one effect. Attempts past the
   cap mark the event `failed` and park the ticket in `needs_review`.
5. **Audit**: append-only rows attribute every transition to agent, human, or
   system. Unique per (ticket, action) so reprocessing can't double-write history.

### Data model

`tickets` (external_id unique, status machine) · `policy_docs` (FTS corpus) ·
`drafts` (reply + citations + grounding verdict) · `approvals` (pending human
decisions) · `outbox_events` (idempotency_key unique, attempts, status) ·
`payments_ledger` (fake provider's ledger, idempotency_key unique) ·
`audit_events` (append-only, per-ticket-action unique).

## Key decisions and tradeoffs

### Postgres as the queue (outbox + SKIP LOCKED), not Redis/Kafka
One system of record, transactional with the business write, zero extra infra,
and multiple workers claim safely. Cost: throughput ceiling lower than a real
broker and polling latency. At helpdesk volumes (thousands/hour) this is far
past sufficient; the swap path is a LISTEN/NOTIFY trigger or moving
`outbox_events` onto a broker without touching handler contracts.

### Postgres FTS for retrieval, not a vector DB
tsvector/ts_rank/ts_headline is deterministic, needs no extension or second
service, and returns verbatim spans - which is what makes citation verification
possible. Cost: no semantic similarity ("my card was billed twice" vs
"duplicate charges" needs the OR-relaxation stage, implemented). pgvector is
the documented upgrade (ROADMAP M4); the retrieval interface doesn't change.

### Rules+threshold risk gate, not an LLM judge
A second model judging the first is unverifiable in CI and drifts with provider
updates. A declarative gate (category allowlist + confidence threshold +
grounding requirement) is testable, explainable in one sentence to a support
lead, and its false-confidence failure mode is bounded: the worst case of a
misfire is an informational email, never a refund. An LLM judge as an
additional signal is roadmap M4.

### Fake payment provider with real semantics, not a mock
The fake keeps a ledger with a unique idempotency key - the same contract
Stripe enforces server-side. Crash-after-commit is simulated with a fault hook
(`RD_PAYMENT_CRASH_AFTER_CHARGE`) that raises after the ledger commit, so the
recovery path (retry sees the row, charges nothing new) is genuinely exercised.
A plain mock returning success would test nothing.

### Citation verification at write time, not prompt promises
The model is asked for verbatim quotes; the system then checks each quote is a
real span of the cited doc and drops any that aren't. Grounding is enforced by
string containment, not hoped for by prompting.

### Sync pipeline at ingest, async side effects
Classification/drafting run inline so an API caller (and the console) sees the
full triage immediately; only real-world effects wait for the worker. Cost:
ingest latency includes an LLM call (~400ms with the stub). Batching ingestion
behind a queue is the M3 change if intake volume demands it.

### Dev-token auth, documented
A single `X-API-Token` header. This is a prototype boundary, stated plainly in
the README rather than dressed up as auth. Real auth + tenancy is M2 because
every table already carries the seams (ticket ownership, actor attribution).

## Failure modes and handling

| Failure | Handling | Test |
| --- | --- | --- |
| Duplicate webhook/re-polled email | `external_id` unique; returns existing | `test_duplicate_ingest_*`, `test_api_duplicate_post_*` |
| Worker crash after charge, before outbox update | Retry's idempotency check sees ledger row; no second charge | `test_worker_crash_mid_refund_recovers_without_double_charge` |
| Worker run twice / duplicate claim | Handlers idempotent; ledger unique key | `test_worker_retry_never_double_charges` |
| LLM garbage JSON / bad category | Ticket parked `needs_review`, `llm_error` audited, nothing half-written | `test_garbage_llm_*` |
| LLM timeout | Same path | `test_timeout_llm_*` |
| Unknown event type | Retries to cap, then `failed` + ticket `needs_review` | `test_unknown_event_type_*` |
| Human double-decision | 409 conflict | `test_decision_twice_conflicts` |
| All approvals rejected | Ticket `needs_review`, human owns next step | `test_reject_all_sends_to_needs_review` |

## Scaling path

1. Intake: move ingest behind a real queue; pipeline workers consume (M3).
2. Retrieval: pgvector embeddings alongside FTS, hybrid rank (M4).
3. Workers: already horizontally safe (SKIP LOCKED); scale by adding replicas.
4. Read path: console queries paginate; audit partitioned by month (M2+).

## Honest limits

- The stub LLM is a rules engine; real generation quality with the OpenAI
  adapter depends on the model and prompts (the same eval harness measures it:
  `LLM_PROVIDER=openai python scripts/eval.py`).
- Seeded tickets are realistic but synthetic; the IMAP adapter is the live
  intake and has been tested against the same pipeline contract.
- Auth is a dev token. Do not expose the API beyond localhost/VPC without M2.
- Load numbers are single-node embedded Postgres; see README for the
  measurement setup.
