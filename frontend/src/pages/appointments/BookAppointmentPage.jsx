import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { bookAppointment, previewVisitType, registerWalkIn } from '../../api/appointments'
import { getPatient } from '../../api/patients'
import { VisitTypeBadge } from '../../components/appointments/Badges'
import DoctorSelect from '../../components/appointments/DoctorSelect'
import PatientPicker from '../../components/appointments/PatientPicker'
import SlotPicker from '../../components/appointments/SlotPicker'
import { cardClass, errorBox, errorMessage, formatDate, inputClass, labelClass, primaryButton, todayISO } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, FRONT_DESK } from '../../routes/roles'

function Step({ n, title, children }) {
  return (
    <section className={cardClass}>
      <h2 className="mb-3 text-sm font-semibold text-slate-800">
        <span className="mr-2 inline-grid h-5 w-5 place-items-center rounded-full bg-brand-gradient text-xs text-white">
          {n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  )
}

function VisitTypeHint({ patientId, doctorId, date }) {
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    if (!patientId || !doctorId || !date) return
    let cancelled = false
    previewVisitType({ patient_id: patientId, doctor_id: doctorId, date }).then((p) => {
      if (!cancelled) setPreview(p)
    })
    return () => {
      cancelled = true
    }
  }, [patientId, doctorId, date])

  if (!preview || !patientId || !doctorId) return null
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
      Visit type: <VisitTypeBadge type={preview.visit_type} />
      <span className="text-xs text-slate-500">
        Last visit {formatDate(preview.last_visit_date)}, last paid {formatDate(preview.last_paid_visit_date)}, follow-up
        window {preview.follow_up_days} days. It can be overridden after booking.
      </span>
    </p>
  )
}

export default function BookAppointmentPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const isFrontDesk = FRONT_DESK.includes(user.role)
  const base = APPOINTMENT_BASE[user.role]

  const [mode, setMode] = useState(isFrontDesk && params.get('mode') === 'walk-in' ? 'walk-in' : 'slot')
  const [patient, setPatient] = useState(null)
  const [doctorId, setDoctorId] = useState(() => params.get('doctor_id') ?? '') // e.g. from the follow-up callback list
  const [date, setDate] = useState(todayISO())
  const [slot, setSlot] = useState('')
  const [slotsVersion, setSlotsVersion] = useState(0) // bump to reload the slot grid
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Opened from a patient profile with ?patient_id=...
  useEffect(() => {
    const pid = params.get('patient_id')
    if (pid) getPatient(pid).then(setPatient).catch(() => {})
  }, [params])

  const walkIn = mode === 'walk-in'
  const day = walkIn ? todayISO() : date
  const ready = patient && doctorId && (walkIn || slot)

  const submit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const appt = walkIn
        ? await registerWalkIn({ patient_id: patient.patient_id, doctor_id: doctorId })
        : await bookAppointment({ patient_id: patient.patient_id, doctor_id: doctorId, date, start_time: slot })
      navigate(`${base}/${appt.id}`)
    } catch (err) {
      setError(errorMessage(err, 'Booking failed'))
      if (err.response?.status === 409) {
        // the slot may have just been taken: reload the grid
        setSlot('')
        setSlotsVersion((v) => v + 1)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">{walkIn ? 'Register walk-in' : 'Book appointment'}</h1>

      {isFrontDesk && (
        <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-sm">
          {[
            ['slot', 'Book a slot'],
            ['walk-in', 'Walk-in (join queue now)'],
          ].map(([m, label]) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`rounded px-3 py-1.5 ${mode === m ? 'bg-brand-gradient text-white' : 'text-slate-600'}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {error && <p className={errorBox}>{error}</p>}

      <Step n={1} title="Patient">
        <PatientPicker value={patient} onChange={setPatient} />
      </Step>

      <Step n={2} title="Doctor">
        <DoctorSelect
          value={doctorId}
          onChange={(id) => {
            setDoctorId(id)
            setSlot('')
          }}
        />
      </Step>

      {!walkIn && (
        <Step n={3} title="Date and time">
          <label className="mb-4 block max-w-xs">
            <span className={labelClass}>Date</span>
            <input
              type="date"
              className={inputClass}
              min={todayISO()}
              required
              value={date}
              onChange={(e) => {
                setDate(e.target.value)
                setSlot('')
              }}
            />
          </label>
          <SlotPicker key={slotsVersion} doctorId={doctorId} date={date} value={slot} onChange={setSlot} />
        </Step>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        {isFrontDesk ? <VisitTypeHint patientId={patient?.patient_id} doctorId={doctorId} date={day} /> : <span />}
        <button className={primaryButton} disabled={!ready || submitting}>
          {submitting ? 'Saving...' : walkIn ? 'Add to queue' : slot ? `Book ${formatDate(date)} at ${slot}` : 'Book'}
        </button>
      </div>
    </form>
  )
}
