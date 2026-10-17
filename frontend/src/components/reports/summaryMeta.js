// Result flags: status colours are reserved for abnormal values and always come with an icon + word
export const RESULT_FLAG = {
  normal: { label: 'Normal', icon: '', className: 'text-slate-600' },
  high: { label: 'High', icon: '▲', className: 'text-amber-800' },
  low: { label: 'Low', icon: '▼', className: 'text-amber-800' },
  abnormal: { label: 'Abnormal', icon: '•', className: 'text-amber-800' },
  critical_high: { label: 'Critical high', icon: '!!', className: 'font-semibold text-red-700' },
  critical_low: { label: 'Critical low', icon: '!!', className: 'font-semibold text-red-700' },
}

export const CONFIDENCE = {
  high: { label: 'High', className: 'bg-accent-50 text-accent-700' },
  medium: { label: 'Medium', className: 'bg-amber-50 text-amber-800' },
  low: { label: 'Low: check original', className: 'bg-red-50 text-red-700' },
}

export const SUMMARY_STATUS = {
  processing: 'AI is reading the report...',
  ready: 'Awaiting doctor review',
  approved: 'Approved',
  failed: 'AI reading failed',
  no_consent: 'Patient has not consented to AI processing',
}

const ORDER = { critical_high: 0, critical_low: 0, high: 1, low: 1, abnormal: 1, normal: 2 }

/** Abnormal and critical first, so the doctor sees what matters at the top. */
export const sortTests = (tests) => [...tests].sort((a, b) => (ORDER[a.flag] ?? 3) - (ORDER[b.flag] ?? 3))
