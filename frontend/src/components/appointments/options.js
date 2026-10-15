export const STATUS_META = {
  scheduled: { label: 'Scheduled', className: 'bg-slate-100 text-slate-700' },
  waiting: { label: 'Waiting', className: 'bg-amber-100 text-amber-800' },
  with_voicebot: { label: 'With voicebot', className: 'bg-violet-100 text-violet-800' },
  in_consultation: { label: 'In consultation', className: 'bg-brand-100 text-brand-800' },
  completed: { label: 'Completed', className: 'bg-accent-100 text-accent-700' },
  cancelled: { label: 'Cancelled', className: 'bg-red-100 text-red-700' },
  no_show: { label: 'No-show', className: 'bg-slate-200 text-slate-600' },
}

export const STATUSES = Object.entries(STATUS_META).map(([value, m]) => ({ value, label: m.label }))

export const VISIT_TYPES = [
  { value: 'new', label: 'New' },
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'returning', label: 'Returning' },
]

export const PAYMENT_STATUSES = [
  { value: 'unpaid', label: 'Unpaid' },
  { value: 'paid', label: 'Paid' },
  { value: 'waived', label: 'Waived' },
]

export const SOURCES = { online: 'Online', front_desk: 'Front desk', walk_in: 'Walk-in' }

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// Queue moves offered as buttons for each status (mirrors the backend's allowed transitions)
export const NEXT_ACTIONS = {
  scheduled: [{ to: 'no_show', label: 'Mark no-show', subtle: true }],
  waiting: [
    { to: 'with_voicebot', label: 'Send to voicebot' },
    { to: 'in_consultation', label: 'Call in' },
    { to: 'no_show', label: 'No-show', subtle: true },
  ],
  with_voicebot: [
    { to: 'in_consultation', label: 'Call in' },
    { to: 'waiting', label: 'Back to waiting', subtle: true },
  ],
  in_consultation: [{ to: 'completed', label: 'Complete' }],
}
