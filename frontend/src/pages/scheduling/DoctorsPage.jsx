import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { createDoctor, listDoctors } from '../../api/doctors'
import { WEEKDAYS } from '../../components/appointments/options'
import { cardClass, errorMessage, inputClass, primaryButton, secondaryButton } from '../../components/ui'

const EMPTY = { full_name: '', email: '', password: '' }

export default function DoctorsPage() {
  const [doctors, setDoctors] = useState([])
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')

  useEffect(() => {
    listDoctors().then(setDoctors)
  }, [])

  const add = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await createDoctor(form)
      setDoctors(await listDoctors())
      setForm(EMPTY)
      setAdding(false)
    } catch (err) {
      setError(errorMessage(err, 'Could not add doctor'))
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-800">Doctors</h1>
        <button className={adding ? secondaryButton : primaryButton} onClick={() => setAdding(!adding)}>
          {adding ? 'Close' : 'Add doctor'}
        </button>
      </div>

      {adding && (
        <form onSubmit={add} className={`${cardClass} grid gap-3 sm:grid-cols-4`}>
          {[
            ['full_name', 'Full name', 'text'],
            ['email', 'Email', 'email'],
            ['password', 'Temporary password (min 8)', 'password'],
          ].map(([key, placeholder, type]) => (
            <input
              key={key}
              className={inputClass}
              type={type}
              placeholder={placeholder}
              required
              minLength={key === 'password' ? 8 : undefined}
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          ))}
          <button className={primaryButton}>Create</button>
          {error && <p className="text-sm text-red-600 sm:col-span-4">{error}</p>}
        </form>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {doctors.map((d) => {
          const days = [...new Set(d.weekly.map((b) => b.weekday))].sort().map((i) => WEEKDAYS[i])
          return (
            <Link key={d.id} to={d.id} className={`${cardClass} transition hover:border-accent-600`}>
              <p className="font-semibold text-slate-800">{d.full_name}</p>
              <p className="text-sm text-slate-500">{d.specialization || 'No specialization set'}</p>
              <p className={`mt-2 text-xs ${days.length ? 'text-slate-500' : 'text-amber-700'}`}>
                {days.length ? `${days.join(', ')} | ${d.slot_minutes} min slots` : 'No working hours yet: not bookable'}
              </p>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
