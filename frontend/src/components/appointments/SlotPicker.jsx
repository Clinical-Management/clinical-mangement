import { useEffect, useState } from 'react'
import { getSlots } from '../../api/doctors'
import { errorMessage } from '../ui'

const SLOT_STYLE = {
  available: 'border-slate-300 bg-white text-slate-700 hover:border-brand-500',
  booked: 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 line-through',
  past: 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-300',
}

/** Slot grid for one doctor and day. `keep` marks the appointment's current slot as selectable. */
export default function SlotPicker({ doctorId, date, value, onChange, keep }) {
  const [day, setDay] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!doctorId || !date) return
    let cancelled = false
    getSlots(doctorId, date)
      .then((d) => {
        if (cancelled) return
        setDay(d)
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Could not load slots'))
      })
    return () => {
      cancelled = true
    }
  }, [doctorId, date])

  if (!doctorId || !date) return <p className="text-sm text-slate-400">Choose a doctor and date to see slots.</p>
  if (error) return <p className="text-sm text-red-600">{error}</p>
  if (!day || day.date !== date || day.doctor_id !== doctorId) return <p className="text-sm text-slate-400">Loading slots...</p>
  if (!day.bookable) return <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{day.reason}</p>

  const free = day.slots.filter((s) => s.status === 'available').length
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">{free} of {day.slots.length} slots free</p>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
        {day.slots.map((s) => {
          const selectable = s.status === 'available' || s.start === keep
          const selected = value === s.start
          return (
            <button
              key={s.start}
              type="button"
              disabled={!selectable}
              onClick={() => onChange(s.start)}
              className={`rounded-md border px-2 py-1.5 text-sm ${
                selected ? 'border-brand-600 bg-brand-600 text-white' : SLOT_STYLE[selectable ? 'available' : s.status]
              }`}
            >
              {s.start}
            </button>
          )
        })}
      </div>
    </div>
  )
}
