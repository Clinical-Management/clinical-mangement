// Shared Tailwind class strings for form controls
export const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500'

export const labelClass = 'mb-1 block text-xs font-medium text-slate-600'

export const buttonClass =
  'w-full rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60'

export const primaryButton =
  'rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60'

export const secondaryButton =
  'rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60'

export const cardClass = 'rounded-xl border border-slate-200 bg-white p-5'

// FastAPI returns `detail` as a string, a list of validation errors, or (for our 409s) an object
export const errorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map((d) => {
        const field = d.loc?.slice(1).join(' > ')
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join('; ')
  if (detail?.message) return detail.message
  return fallback
}

// Plain YYYY-MM-DD values are calendar dates: parse them as local, not UTC midnight
const toDate = (value) => new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00` : value)

export const formatDate = (value) =>
  value ? toDate(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '-'

export const formatDay = (value) =>
  value ? toDate(value).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) : '-'

export const formatTime = (value) =>
  value ? new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : '-'

// Local calendar date as YYYY-MM-DD (the clinic and its staff share a timezone)
export const todayISO = () => new Date().toLocaleDateString('en-CA')

export const errorBox = 'rounded-md bg-red-50 px-4 py-3 text-sm text-red-700'
