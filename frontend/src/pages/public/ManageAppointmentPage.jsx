import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { publicAppointment, publicCancel, publicConfirm, publicReschedule, publicSlots } from '../../api/reminders'
import Logo from '../../components/Logo'
import { errorMessage, formatDate, inputClass, primaryButton, secondaryButton, todayISO } from '../../components/ui'

const STATUS = { scheduled: 'Booked', cancelled: 'Cancelled', completed: 'Completed', waiting: 'Checked in', no_show: 'Missed' }

const time12 = (hhmm) => {
  if (!hhmm) return ''
  const [h, m] = hhmm.split(':').map(Number)
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

/** Opened from a reminder (no login): confirm, pick another time, or cancel. */
export default function ManageAppointmentPage() {
  const { appointmentId } = useParams()
  const [params] = useSearchParams()
  const token = params.get('t') ?? ''
  const autoConfirm = params.get('do') === 'confirm'
  const [appt, setAppt] = useState(null)
  const [mode, setMode] = useState(null) // 'reschedule' | 'cancel'
  const [day, setDay] = useState(todayISO())
  const [slots, setSlots] = useState(null)
  const [reason, setReason] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const confirmedOnce = useRef(false)

  useEffect(() => {
    const load = async () => {
      try {
        let a = await publicAppointment(appointmentId, token)
        // the "Confirm" link in the message confirms straight away
        if (autoConfirm && !confirmedOnce.current && a.can_change && !a.confirmed) {
          confirmedOnce.current = true
          a = await publicConfirm(appointmentId, token)
          setNotice('Thank you, your appointment is confirmed.')
        }
        setAppt(a)
      } catch (err) {
        setError(errorMessage(err, 'This link is not valid'))
      }
    }
    load()
  }, [appointmentId, token, autoConfirm])

  useEffect(() => {
    if (mode !== 'reschedule') return
    publicSlots(appointmentId, token, day)
      .then(setSlots)
      .catch(() => setSlots({ bookable: false, slots: [] }))
  }, [mode, day, appointmentId, token])

  const act = async (fn, done) => {
    setError('')
    try {
      setAppt(await fn())
      setNotice(done)
      setMode(null)
    } catch (err) {
      setError(errorMessage(err, 'Something went wrong'))
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="mx-auto max-w-md space-y-5">
        <Logo />
        {error && <p className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
        {!appt && !error && <p className="text-slate-500">Loading...</p>}
        {appt && (
          <>
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-sm text-slate-500">{appt.clinic_name}</p>
              <h1 className="mt-1 text-xl font-semibold text-slate-800">
                {appt.patient_first_name}&apos;s appointment with {appt.doctor_name}
              </h1>
              <p className="mt-3 text-2xl font-semibold text-brand-700">
                {formatDate(appt.date)}
                {appt.start_time && <span className="block text-lg text-slate-700">{time12(appt.start_time)}</span>}
              </p>
              <p className="mt-2 text-sm">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${appt.status === 'scheduled' ? 'bg-accent-100 text-accent-700' : 'bg-slate-100 text-slate-600'}`}>
                  {STATUS[appt.status] ?? appt.status}
                </span>
                {appt.confirmed && appt.status === 'scheduled' && <span className="ml-2 text-accent-700">✓ Confirmed</span>}
              </p>
            </div>
            {notice && <p className="rounded-md bg-accent-50 px-4 py-3 text-sm text-accent-800">{notice}</p>}

            {appt.can_change && !mode && (
              <div className="grid gap-2">
                {!appt.confirmed && (
                  <button className={primaryButton} onClick={() => act(() => publicConfirm(appointmentId, token), 'Thank you, your appointment is confirmed.')}>
                    Confirm I&apos;ll come
                  </button>
                )}
                <button className={secondaryButton} onClick={() => setMode('reschedule')}>
                  Change the time
                </button>
                <button className="py-2 text-sm text-red-600 hover:underline" onClick={() => setMode('cancel')}>
                  Cancel the appointment
                </button>
              </div>
            )}

            {mode === 'reschedule' && (
              <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
                <input type="date" className={inputClass} min={todayISO()} value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" />
                {!slots ? (
                  <p className="text-sm text-slate-500">Loading times...</p>
                ) : !slots.bookable ? (
                  <p className="text-sm text-slate-500">{slots.reason ?? 'No times on this day.'}</p>
                ) : (
                  <div className="grid grid-cols-3 gap-2">
                    {slots.slots
                      .filter((s) => s.status === 'available')
                      .map((s) => (
                        <button
                          key={s.start}
                          className="rounded-md border border-brand-200 py-2 text-sm text-brand-700 hover:bg-brand-50"
                          onClick={() => act(() => publicReschedule(appointmentId, token, { date: day, start_time: s.start }), 'Your appointment has been moved.')}
                        >
                          {time12(s.start)}
                        </button>
                      ))}
                    {!slots.slots.some((s) => s.status === 'available') && <p className="col-span-3 text-sm text-slate-500">All times are taken on this day.</p>}
                  </div>
                )}
                <button className="text-sm text-slate-500 hover:underline" onClick={() => setMode(null)}>
                  Back
                </button>
              </div>
            )}

            {mode === 'cancel' && (
              <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
                <input className={inputClass} placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
                <div className="flex gap-2">
                  <button className={secondaryButton} onClick={() => setMode(null)}>
                    Keep it
                  </button>
                  <button
                    className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
                    onClick={() => act(() => publicCancel(appointmentId, token, reason.trim() || null), 'Your appointment has been cancelled.')}
                  >
                    Cancel appointment
                  </button>
                </div>
              </div>
            )}

            {appt.clinic_phone && <p className="text-center text-sm text-slate-500">Questions? Call {appt.clinic_phone}</p>}
          </>
        )}
      </div>
    </div>
  )
}
