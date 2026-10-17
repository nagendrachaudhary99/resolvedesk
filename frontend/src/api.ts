// Thin API client. The dev token is a prototype convenience - see DESIGN.md "Auth".
export const API = '/api'
export const TOKEN = 'dev-token'

export interface Citation { doc_slug: string; doc_title: string; quote: string }
export interface Draft {
  id: string; reply_text: string; citations: Citation[]; confidence: number
  grounded_ok: boolean; route: string; llm_model: string; created_at: string
}
export interface Approval {
  id: string; action_type: string; payload: Record<string, unknown>
  status: string; decided_by: string | null
}
export interface Ticket {
  id: string; subject: string; status: string; category: string | null
  confidence: number | null; customer_email: string; created_at: string
  body?: string; drafts?: Draft[]; approvals?: Approval[]
}
export interface ApprovalRow {
  id: string; ticket_id: string; action_type: string
  payload: Record<string, unknown>; status: string
  ticket_subject: string; customer_email: string; created_at: string
}
export interface AuditEvent {
  id: string; ticket_id: string; actor: string; action: string
  detail: Record<string, unknown>; created_at: string
}

export async function getTickets(status?: string): Promise<Ticket[]> {
  const q = status ? `?status=${status}` : ''
  const r = await fetch(`${API}/tickets${q}`)
  return r.json()
}
export async function getTicket(id: string): Promise<Ticket> {
  const r = await fetch(`${API}/tickets/${id}`)
  return r.json()
}
export async function getApprovals(): Promise<ApprovalRow[]> {
  const r = await fetch(`${API}/approvals`)
  return r.json()
}
export async function decide(id: string, decision: 'approve' | 'reject'): Promise<void> {
  await fetch(`${API}/approvals/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Token': TOKEN },
    body: JSON.stringify({ decision, decided_by: 'console-user' }),
  })
}
export async function getAudit(ticketId?: string): Promise<AuditEvent[]> {
  const q = ticketId ? `?ticket_id=${ticketId}` : ''
  const r = await fetch(`${API}/audit${q}`)
  return r.json()
}
