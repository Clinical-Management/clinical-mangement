import { useEffect, useState } from 'react'
import { addLeave, deleteLeave, listLeaves } from '../../api/doctors'
import { cardClass, errorMessage, formatDate, inputClass, labelClass, primaryButton, todayISO } from '../ui'
import ConflictList from './ConflictList'

export default function LeavesPanel({ doctorId }) {
  const [leaves, setLeaves] = useState([])
  const [form, setForm] = useState({ start_date: todayISO(), end_date: todayISO(), reason: '' })
  const [conflicts, setConflicts] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    listLeaves(doctorId).then(setLeaves)
  }, [doctorId])

  const add = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const { conflicting_appointments } = await addLeave(doctorId, { ...form, reason: form.reason || null })
      setConflicts(conflicting_appointments)
      setLeaves(await listLeaves(doctorId))
      setForm({ ...form, reason: '' })
    } catch (err) {
      setError(errorMessage(err, 'Could not add leave'))
    }
  }

  const remove = async (id) => {
    await deleteLeave(doctorId, id)
    setLeaves(leaves.filter((l) => l.id !== id))
  }

  return (
    <section className={`${cardClass} space-y-4`}>
      <h2 className="text-sm font-semibold text-slate-800">Leave</h2>
      <ConflictList appointments={conflicts} onClose={() => setConflicts([])} />

      {leaves.length === 0 ? (
        <p className="text-sm text-slate-400">No upcoming leave.</p>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {leaves.map((l) => (
            <li key={l.id} className="flex items-center justify-between py-2">
              <span>
                {formatDate(l.start_date)}
                {l.end_date !== l.start_date && ` to ${formatDate(l.end_date)}`}
                {l.reason && <span className="ml-2 text-slate-500">{l.reason}</span>}
              </span>
              <button className="text-red-600 hover:underline" onClick={() => remove(l.id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-4">
        {[
          ['start_date', 'From'],
          ['end_date', 'To'],
        ].map(([key, label]) => (
          <label key={key}>
            <span className={labelClass}>{label}</span>
            <input
              type="date"
              required
              min={todayISO()}
              className={inputClass}
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </label>
        ))}
        <label className="min-w-40 flex-1">
          <span className={labelClass}>Reason</span>
          <input className={inputClass} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </label>
        <button className={primaryButton}>Add leave</button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  )
}
