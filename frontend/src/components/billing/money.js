// Paise <-> rupees for display and inputs (the API works in paise)
export const rupees = (paise) =>
  `₹${(Number(paise || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: paise % 100 ? 2 : 0, maximumFractionDigits: 2 })}`

export const toPaise = (text) => {
  const n = Number(String(text).replace(/[^\d.]/g, ''))
  return Number.isFinite(n) ? Math.round(n * 100) : 0
}

export const toRupeeInput = (paise) => (paise ? String(paise / 100) : '')

export const GST_RATES = [0, 5, 12, 18, 28]

export const MODES = [
  ['cash', 'Cash'],
  ['upi', 'UPI'],
  ['card', 'Card'],
  ['other', 'Other'],
]

export const VISIT_FEES = [
  ['new', 'New visit'],
  ['follow_up', 'Follow-up'],
  ['returning', 'Returning'],
  ['emergency', 'Emergency / after-hours'],
  ['teleconsultation', 'Teleconsultation'],
]

export const ITEM_KINDS = [
  ['procedure', 'Procedure'],
  ['injection', 'Injection'],
  ['dressing', 'Dressing'],
  ['test', 'In-clinic test'],
  ['medicine', 'Medicine'],
  ['other', 'Other'],
]

export const STATUS_STYLE = {
  paid: 'bg-accent-100 text-accent-700',
  partial: 'bg-amber-100 text-amber-800',
  unpaid: 'bg-slate-100 text-slate-700',
  waived: 'bg-brand-100 text-brand-700',
  cancelled: 'bg-red-100 text-red-700',
}
