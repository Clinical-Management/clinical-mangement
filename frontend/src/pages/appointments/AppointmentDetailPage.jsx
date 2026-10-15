import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  cancelAppointment,
  checkIn,
  clearVisitTypeOverride,
  getAppointment,
  overrideVisitType,
  reschedule,
  updatePayment,
  updateStatus,
} from '../../api/appointments'
import { StatusBadge, VisitTypeBadge } from '../../components/appointments/Badges'
import { NEXT_ACTIONS, PAYMENT_STATUSES, SOURCES, STATUS_META, VISIT_TYPES } from '../../components/appointments/options'
import SlotPicker from '../../components/appointments/SlotPicker'
import { labelOf } from '../../components/patients/options'
import {
  cardClass,
  errorBox,
  errorMessage,
  formatDate,
  formatTime,
  inputClass,
  labelClass,
  primaryButton,
  secondaryButton,
  todayISO,
} from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { FRONT_DESK, PATIENT_BASE, ROLES } from '../../routes/roles'

function Detail({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-800">{children}</dd>
    </div>
  )
}

function ReschedulePanel({ appt, onDone, run }) {
  const [date, setDate] = useState(appt.date)
  const [slot, setSlot] = useState(appt.start_time ?? '')
  const changed = date !== appt.date || slot !== appt.start_time

  return (
    <div className="space-y-3">
      <label className="block max-w-xs">
        <span className={labelClass}>New date</span>
        <input
          type="date"
          className={inputClass}
          min={todayISO()}
          value={date}
          onChange={(e) => {
            setDate(e.target.value)
            setSlot('')
          }}
        />
      </label>
      <SlotPicker
        doctorId={appt.doctor_id}
        date={date}
        value={slot}
        onChange={setSlot}
        keep={date === appt.date ? appt.start_time : undefined}
      />
      <div className="flex gap-2">
        <button className={secondaryButton} onClick={onDone}>
          Close
        </button>
        <button
          className={primaryButton}
          disabled={!slot || !changed}
          onClick={() => run(() => reschedule(appt.id, { date, start_time: slot })).then((ok) => ok && onDone())}
        >
          Move to {formatDate(date)} {slot}
        </button>
      </div>
    </div>
  )
}

function OverridePanel({ appt, run, onDone }) {
  const [visitType, setVisitType] = useState(appt.visit_type)
  const [reason, setReason] = useState('')

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        run(() => overrideVisitType(appt.id, { visit_type: visitType, reason })).then((ok) => ok && onDone())
      }}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <label>
          <span className={labelClass}>Visit type</span>
          <select className={inputClass} value={visitType} onChange={(e) => setVisitType(e.target.value)}>
            {VISIT_TYPES.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label className="sm:col-span-2">
          <span className={labelClass}>Reason (required)</span>
          <input
            className={inputClass}
            required
            minLength={3}
            maxLength={300}
            placeholder="e.g. Referred back by Dr Shah for the same complaint"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
      </div>
      <div className="flex gap-2">
        <button type="button" className={secondaryButton} onClick={onDone}>
          Close
        </button>
        <button className={primaryButton}>Save override</button>
      </div>
    </form>
  )
}

export default function AppointmentDetailPage() {
  const { appointmentId } = useParams()
  const { user } = useAuth()
  const [appt, setAppt] = useState(null)
  const [error, setError] = useState('')
  const [panel, setPanel] = useState(null) // 'reschedule' | 'override' | 'cancel'
  const [cancelReason, setCancelReason] = useState('')

  const isFrontDesk = FRONT_DESK.includes(user.role)
  const isDoctor = user.role === ROLES.DOCTOR
  const isOwner = user.role === ROLES.PATIENT

  useEffect(() => {
    getAppointment(appointmentId)
      .then(setAppt)
      .catch((err) => setError(errorMessage(err, 'Could not load appointment')))
  }, [appointmentId])

  // Runs an API action, stores the updated appointment; resolves true on success
  const run = async (action) => {
    setError('')
    try {
      setAppt(await action())
      return true
    } catch (err) {
      setError(errorMessage(err, 'Action failed'))
      return false
    }
  }

  if (!appt) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Loading...</p>

  const scheduled = appt.status === 'scheduled'
  const canChange = scheduled && (isFrontDesk || (isOwner && appt.source !== 'walk_in'))
  const canCancel = canChange || (isFrontDesk && appt.status === 'waiting')
  const queueActions = isFrontDesk || isDoctor ? (NEXT_ACTIONS[appt.status] ?? []) : []

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">
            {appt.patient_name} with {appt.doctor_name}
          </h1>
          <p className="text-sm text-slate-500">
            {formatDate(appt.date)}
            {appt.start_time ? ` at ${appt.start_time}-${appt.end_time}` : ' (walk-in)'}
            {appt.token && ` | Token #${appt.token}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <VisitTypeBadge type={appt.visit_type} overridden={!!appt.visit_type_override} />
          <StatusBadge status={appt.status} />
        </div>
      </div>

      {error && <p className={errorBox}>{error}</p>}

      <section className={cardClass}>
        <dl className="grid gap-4 sm:grid-cols-3">
          <Detail label="Patient">
            {isOwner ? (
              appt.patient_id
            ) : (
              <Link to={`${PATIENT_BASE[user.role]}/${appt.patient_id}`} className="font-mono text-brand-700 hover:underline">
                {appt.patient_id}
              </Link>
            )}
          </Detail>
          <Detail label="Booked via">{SOURCES[appt.source]}</Detail>
          <Detail label="Payment">{labelOf(PAYMENT_STATUSES, appt.payment_status)}</Detail>
          <Detail label="Checked in">{appt.checked_in_at ? formatTime(appt.checked_in_at) : '-'}</Detail>
          <Detail label="Detected visit type">{labelOf(VISIT_TYPES, appt.visit_type_auto)}</Detail>
          {appt.cancel_reason && <Detail label="Cancellation reason">{appt.cancel_reason}</Detail>}
        </dl>
        {appt.visit_type_override && (
          <p className="mt-4 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
            Visit type set to <b>{labelOf(VISIT_TYPES, appt.visit_type_override.visit_type)}</b> by{' '}
            {appt.visit_type_override.by_role}: "{appt.visit_type_override.reason}"
          </p>
        )}
      </section>

      {(isFrontDesk || queueActions.length > 0 || canChange || canCancel) && (
        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Actions</h2>
          <div className="flex flex-wrap gap-2">
            {isFrontDesk && scheduled && appt.date === todayISO() && (
              <button className={primaryButton} onClick={() => run(() => checkIn(appt.id))}>
                Check in
              </button>
            )}
            {queueActions.map((a) => (
              <button
                key={a.to}
                className={a.subtle ? secondaryButton : primaryButton}
                onClick={() => run(() => updateStatus(appt.id, a.to))}
              >
                {a.label}
              </button>
            ))}
            {canChange && (
              <button className={secondaryButton} onClick={() => setPanel('reschedule')}>
                Reschedule
              </button>
            )}
            {canCancel && (
              <button className={secondaryButton} onClick={() => setPanel('cancel')}>
                Cancel appointment
              </button>
            )}
            {isFrontDesk && !['cancelled', 'no_show'].includes(appt.status) && (
              <button className={secondaryButton} onClick={() => setPanel('override')}>
                Override visit type
              </button>
            )}
            {isFrontDesk && appt.visit_type_override && (
              <button className={secondaryButton} onClick={() => run(() => clearVisitTypeOverride(appt.id))}>
                Use detected type
              </button>
            )}
            {isFrontDesk && (
              <select
                className={`${inputClass} w-auto`}
                value={appt.payment_status}
                onChange={(e) => run(() => updatePayment(appt.id, e.target.value))}
                title="Payment status"
              >
                {PAYMENT_STATUSES.map((p) => (
                  <option key={p.value} value={p.value}>
                    Payment: {p.label}
                  </option>
                ))}
              </select>
            )}
          </div>

          {panel && (
            <div className="mt-4 border-t border-slate-100 pt-4">
              {panel === 'reschedule' && <ReschedulePanel appt={appt} run={run} onDone={() => setPanel(null)} />}
              {panel === 'override' && <OverridePanel appt={appt} run={run} onDone={() => setPanel(null)} />}
              {panel === 'cancel' && (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="min-w-64 flex-1">
                    <span className={labelClass}>Reason (optional)</span>
                    <input className={inputClass} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
                  </label>
                  <button className={secondaryButton} onClick={() => setPanel(null)}>
                    Keep appointment
                  </button>
                  <button
                    className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
                    onClick={() => run(() => cancelAppointment(appt.id, cancelReason)).then((ok) => ok && setPanel(null))}
                  >
                    Cancel appointment
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      <section className={cardClass}>
        <h2 className="mb-3 text-sm font-semibold text-slate-800">History</h2>
        <ul className="space-y-1.5 text-sm text-slate-600">
          {[
            ...appt.status_history.map((h) => ({ at: h.at, text: STATUS_META[h.status]?.label ?? h.status, by: h.by_role })),
            ...appt.reschedule_history.map((h) => ({
              at: h.at,
              text: `Rescheduled from ${formatDate(h.from_date)} ${h.from_time ?? ''} to ${formatDate(h.to_date)} ${h.to_time}`,
              by: h.by_role,
            })),
          ]
            .sort((a, b) => new Date(a.at) - new Date(b.at))
            .map((h, i) => (
              <li key={i}>
                <span className="text-slate-400">
                  {formatDate(h.at)} {formatTime(h.at)}
                </span>{' '}
                {h.text} <span className="text-slate-400">by {h.by}</span>
              </li>
            ))}
        </ul>
      </section>
    </div>
  )
}
