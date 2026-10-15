import { labelOf } from '../patients/options'
import { STATUS_META, VISIT_TYPES } from './options'

export function StatusBadge({ status }) {
  const meta = STATUS_META[status] ?? { label: status, className: 'bg-slate-100 text-slate-700' }
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>{meta.label}</span>
}

const VISIT_STYLE = {
  new: 'border-sky-200 bg-sky-50 text-sky-800',
  follow_up: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  returning: 'border-slate-200 bg-slate-50 text-slate-700',
}

export function VisitTypeBadge({ type, overridden }) {
  return (
    <span
      className={`rounded border px-2 py-0.5 text-xs font-medium ${VISIT_STYLE[type]}`}
      title={overridden ? 'Set manually by the front desk' : 'Detected automatically'}
    >
      {labelOf(VISIT_TYPES, type)}
      {overridden && ' *'}
    </span>
  )
}
