import { useCallback, useEffect, useState } from 'react'
import {
  ApprovalRow, AuditEvent, Ticket, decide, getApprovals, getAudit, getTicket, getTickets,
} from './api'

type View = 'inbox' | 'approvals' | 'audit'

export default function App() {
  const [view, setView] = useState<View>('inbox')
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [approvals, setApprovals] = useState<ApprovalRow[]>([])
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [selected, setSelected] = useState<Ticket | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [t, a, au] = await Promise.all([getTickets(), getApprovals(), getAudit()])
      setTickets(t)
      setApprovals(a)
      setAudit(au)
    } catch {
      /* API not up yet - the console retries on the next tick */
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  const openTicket = async (id: string) => setSelected(await getTicket(id))

  return (
    <>
      <header>
        <h1><span className="dot" />ResolveDesk</h1>
        <nav>
          <button className={view === 'inbox' ? 'active' : ''} onClick={() => setView('inbox')}>
            Inbox
          </button>
          <button className={view === 'approvals' ? 'active' : ''} onClick={() => setView('approvals')}>
            Approvals{approvals.length > 0 && <span className="badge">{approvals.length}</span>}
          </button>
          <button className={view === 'audit' ? 'active' : ''} onClick={() => setView('audit')}>
            Audit trail
          </button>
        </nav>
      </header>
      <main>
        {view === 'inbox' && (
          <Inbox tickets={tickets} selected={selected} onOpen={openTicket} onClose={() => setSelected(null)} />
        )}
        {view === 'approvals' && (
          <Approvals approvals={approvals} onDecide={async (id, d) => { await decide(id, d); refresh() }} />
        )}
        {view === 'audit' && <Audit events={audit} />}
      </main>
    </>
  )
}

function StatusPill({ status }: { status: string }) {
  return <span className={`pill ${status}`}>{status.replace(/_/g, ' ')}</span>
}

function Inbox({ tickets, selected, onOpen, onClose }: {
  tickets: Ticket[]; selected: Ticket | null
  onOpen: (id: string) => void; onClose: () => void
}) {
  if (selected) return <TicketDetail ticket={selected} onClose={onClose} />
  return (
    <>
      <h3>Tickets ({tickets.length})</h3>
      {tickets.map((t) => (
        <div className="card clickable" key={t.id} onClick={() => onOpen(t.id)}>
          <div className="row">
            <div>
              <div>{t.subject}</div>
              <div className="muted">
                {t.customer_email} · {t.category ?? 'unclassified'}
                {t.confidence != null && ` · ${(t.confidence * 100).toFixed(0)}%`}
              </div>
            </div>
            <StatusPill status={t.status} />
          </div>
        </div>
      ))}
      {tickets.length === 0 && <p className="muted">No tickets yet. Seed some with the worker or POST /tickets.</p>}
    </>
  )
}

function TicketDetail({ ticket, onClose }: { ticket: Ticket; onClose: () => void }) {
  const draft = ticket.drafts?.[0]
  return (
    <>
      <div className="row">
        <h3>{ticket.subject}</h3>
        <button className="act" onClick={onClose}>Back</button>
      </div>
      <div className="muted">
        {ticket.customer_email} · <StatusPill status={ticket.status} />
      </div>
      <div className="card" style={{ marginTop: 12 }}>
        <div className="muted">Customer message</div>
        <div className="draft">{ticket.body}</div>
      </div>
      {draft && (
        <div className="card">
          <div className="row">
            <div className="muted">
              Agent draft · {draft.llm_model} · {(draft.confidence * 100).toFixed(0)}% confidence ·{' '}
              {draft.grounded_ok ? 'grounded' : 'ungrounded'} · routed {draft.route}
            </div>
          </div>
          <div className="draft">{draft.reply_text}</div>
          {draft.citations.map((c, i) => (
            <div className="cite" key={i}>
              <div className="src">{c.doc_title} ({c.doc_slug})</div>
              {c.quote}
            </div>
          ))}
        </div>
      )}
      {(ticket.approvals?.length ?? 0) > 0 && (
        <div className="card">
          <div className="muted">Approvals</div>
          {ticket.approvals!.map((a) => (
            <div className="row" key={a.id} style={{ marginTop: 6 }}>
              <span>
                {a.action_type}
                {a.action_type === 'refund' && (
                  <span className="amount"> ${(Number(a.payload.amount_cents) / 100).toFixed(2)}</span>
                )}
              </span>
              <span className={`pill ${a.status === 'pending' ? 'pending_approval' : 'resolved'}`}>{a.status}</span>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function Approvals({ approvals, onDecide }: {
  approvals: ApprovalRow[]; onDecide: (id: string, d: 'approve' | 'reject') => void
}) {
  return (
    <>
      <h3>Pending approvals ({approvals.length})</h3>
      <p className="muted">Money movement and account changes always land here. The agent drafted everything; a human decides.</p>
      {approvals.map((a) => (
        <div className="card" key={a.id}>
          <div className="row">
            <div>
              <div>
                <b>{a.action_type}</b>
                {a.action_type === 'refund' && (
                  <span className="amount"> ${(Number(a.payload.amount_cents) / 100).toFixed(2)}</span>
                )}
                {' · '}{a.ticket_subject}
              </div>
              <div className="muted">{a.customer_email}</div>
            </div>
            <div>
              <button className="act approve" onClick={() => onDecide(a.id, 'approve')}>Approve</button>
              <button className="act reject" onClick={() => onDecide(a.id, 'reject')}>Reject</button>
            </div>
          </div>
          {a.action_type === 'send_reply' && <div className="draft">{String(a.payload.body ?? '')}</div>}
        </div>
      ))}
      {approvals.length === 0 && <p className="muted">Queue is empty.</p>}
    </>
  )
}

function Audit({ events }: { events: AuditEvent[] }) {
  return (
    <>
      <h3>Audit trail</h3>
      <p className="muted">Every state change, attributed: agent, human, or system. Append-only.</p>
      <div className="timeline">
        {events.map((e) => (
          <div className={`ev ${e.actor}`} key={e.id}>
            <div>
              <b>{e.action}</b> <span className="muted">by {e.actor}</span>
            </div>
            <div className="muted">
              {new Date(e.created_at).toLocaleString()} · ticket {e.ticket_id.slice(0, 8)}
              {Object.keys(e.detail).length > 0 && ` · ${JSON.stringify(e.detail)}`}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
