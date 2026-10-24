import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getDoctor, saveSchedule } from '../../api/doctors'
import LeavesPanel from '../../components/appointments/LeavesPanel'
import WeeklySchedule from '../../components/appointments/WeeklySchedule'
import CredentialsPanel from '../../components/prescriptions/CredentialsPanel'
import { cardClass, errorBox, errorMessage, inputClass, labelClass, primaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { ROLES } from '../../routes/roles'

/** Admins edit any doctor's schedule; doctors see their own (read-only) and manage their leave. */
export default function DoctorSchedulePage() {
  const { user } = useAuth()
  const params = useParams()
  const isAdmin = user.role === ROLES.ADMIN
  const doctorId = params.doctorId ?? user.id

  const [doctor, setDoctor] = useState(null)
  const [form, setForm] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getDoctor(doctorId)
      .then((d) => {
        setDoctor(d)
        setForm({
          specialization: d.specialization ?? '',
          slot_minutes: d.slot_minutes,
          follow_up_days: d.follow_up_days,
          free_follow_ups: d.free_follow_ups ?? '',
          fees: Object.fromEntries(['new', 'follow_up', 'returning', 'emergency', 'teleconsultation'].map((k) => [k, d.fees?.[k] ?? ''])),
          weekly: d.weekly,
        })
      })
      .catch((err) => setError(errorMessage(err, 'Could not load doctor')))
  }, [doctorId])

  const save = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')
    try {
      const saved = await saveSchedule(doctorId, {
        ...form,
        specialization: form.specialization || null,
        slot_minutes: Number(form.slot_minutes),
        follow_up_days: Number(form.follow_up_days),
        free_follow_ups: form.free_follow_ups === '' ? null : Number(form.free_follow_ups),
        fees: Object.fromEntries(Object.entries(form.fees).map(([k, v]) => [k, v === '' ? null : Number(v)])),
      })
      setDoctor(saved)
      setMessage('Schedule saved. Existing bookings are kept.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save schedule'))
    }
  }

  if (!form) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Loading...</p>

  const number = (key, props) => (
    <input
      type="number"
      className={inputClass}
      required
      value={form[key]}
      disabled={!isAdmin}
      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      {...props}
    />
  )

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">{isAdmin ? doctor.full_name : 'My schedule'}</h1>
      {error && <p className={errorBox}>{error}</p>}
      {message && <p className="rounded-md bg-accent-50 px-4 py-3 text-sm text-accent-700">{message}</p>}

      <form onSubmit={save} className={`${cardClass} space-y-5`}>
        <div className="grid gap-4 sm:grid-cols-3">
          <label>
            <span className={labelClass}>Specialization</span>
            <input
              className={inputClass}
              value={form.specialization}
              disabled={!isAdmin}
              onChange={(e) => setForm({ ...form, specialization: e.target.value })}
            />
          </label>
          <label>
            <span className={labelClass}>Slot length (minutes)</span>
            {number('slot_minutes', { min: 5, max: 120 })}
          </label>
          <label>
            <span className={labelClass}>Follow-up window (days after a paid visit)</span>
            {number('follow_up_days', { min: 0, max: 365 })}
          </label>
          <label>
            <span className={labelClass}>Follow-ups allowed in the window (blank = no limit)</span>
            {number('free_follow_ups', { min: 0, max: 20, required: false, placeholder: 'No limit' })}
          </label>
        </div>

        <div>
          <h2 className="mb-1 text-sm font-semibold text-slate-800">Consultation fees (₹)</h2>
          <p className="mb-2 text-xs text-slate-500">Billing fills these in automatically from the visit type. Left blank, the specialty&apos;s fee from the billing settings applies.</p>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              ['new', 'New visit'],
              ['follow_up', 'Follow-up (within window)'],
              ['returning', 'Returning'],
              ['emergency', 'Emergency / after-hours'],
              ['teleconsultation', 'Teleconsultation'],
            ].map(([key, label]) => (
              <label key={key}>
                <span className={labelClass}>{label}</span>
                <input
                  type="number"
                  min={0}
                  className={inputClass}
                  placeholder="Not set"
                  value={form.fees[key]}
                  disabled={!isAdmin}
                  onChange={(e) => setForm({ ...form, fees: { ...form.fees, [key]: e.target.value } })}
                />
              </label>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-1 text-sm font-semibold text-slate-800">Weekly working hours</h2>
          <WeeklySchedule blocks={form.weekly} readOnly={!isAdmin} onChange={(weekly) => setForm({ ...form, weekly })} />
        </div>

        {isAdmin && (
          <div className="flex justify-end">
            <button className={primaryButton}>Save schedule</button>
          </div>
        )}
      </form>

      <CredentialsPanel doctor={doctor} />

      <LeavesPanel doctorId={doctorId} />
    </div>
  )
}
