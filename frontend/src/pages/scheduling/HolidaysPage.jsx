import { useEffect, useState } from 'react'
import { addHoliday, deleteHoliday, listHolidays } from '../../api/doctors'
import ConflictList from '../../components/appointments/ConflictList'
import { cardClass, errorMessage, formatDay, inputClass, primaryButton, todayISO } from '../../components/ui'

export default function HolidaysPage() {
  const [holidays, setHolidays] = useState([])
  const [form, setForm] = useState({ date: todayISO(), name: '' })
  const [conflicts, setConflicts] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    listHolidays().then(setHolidays)
  }, [])

  const add = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const { conflicting_appointments } = await addHoliday(form)
      setConflicts(conflicting_appointments)
      setHolidays(await listHolidays())
      setForm({ ...form, name: '' })
    } catch (err) {
      setError(errorMessage(err, 'Could not add holiday'))
    }
  }

  const remove = async (id) => {
    await deleteHoliday(id)
    setHolidays(holidays.filter((h) => h.id !== id))
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">Clinic holidays</h1>
        <p className="text-sm text-slate-500">No doctor can be booked on these days.</p>
      </div>

      <ConflictList appointments={conflicts} onClose={() => setConflicts([])} />

      <form onSubmit={add} className={`${cardClass} flex flex-wrap items-center gap-2`}>
        <input
          type="date"
          required
          min={todayISO()}
          className={`${inputClass} w-auto`}
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
        <input
          required
          className={`${inputClass} min-w-48 flex-1`}
          placeholder="Holiday name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <button className={primaryButton}>Add holiday</button>
        {error && <p className="w-full text-sm text-red-600">{error}</p>}
      </form>

      <section className={cardClass}>
        {holidays.length === 0 ? (
          <p className="text-sm text-slate-400">No upcoming holidays.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {holidays.map((h) => (
              <li key={h.id} className="flex items-center justify-between py-2">
                <span>
                  <span className="inline-block w-32 text-slate-500">{formatDay(h.date)}</span>
                  {h.name}
                </span>
                <button className="text-red-600 hover:underline" onClick={() => remove(h.id)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
