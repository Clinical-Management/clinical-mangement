import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getReminderSettings, listCallbacks, listNotifications, recordCall, runNotificationsNow, saveReminderSettings } from '../../api/reminders'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, labelClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, PATIENT_BASE, ROLES } from '../../routes/roles'

const OUTCOMES = [
  ['no_answer', 'No answer'],
  ['will_book', 'Will book'],
  ['booked', 'Booked'],
  ['declined', 'Declined'],
  ['not_needed', 'Not needed'],
]
const KINDS = { reminder: 'Reminder', follow_up_booked: 'Follow-up booked', follow_up_nudge: 'Follow-up nudge', medicine: 'Medicine', repeat_test: 'Repeat test' }
const STATUS_STYLE = { sent: 'text-accent-700', failed: 'text-red-700', not_configured: 'text-amber-700', scheduled: 'text-slate-500', cancelled: 'text-slate-400' }
const STATUS_TEXT = { not_configured: 'not set up', sending: 'sending' }

function Callbacks({ base }) {
  const [rows, setRows] = useState(null)
  const [showClosed, setShowClosed] = useState(false)
  const [notes, setNotes] = useState({})

  useEffect(() => {
    listCallbacks(showClosed).then(setRows)
  }, [showClosed])

  const log = async (row, outcome) => {
    await recordCall(row.appointment_id, { outcome, note: notes[row.appointment_id]?.trim() || null })
    setRows(await listCallbacks(showClosed))
  }

  if (!rows) return <p className="text-slate-500">Loading...</p>
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Patients whose advised follow-up is due soon or overdue, with nothing booked.</p>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
          Show declined
        </label>
      </div>
      {!rows.length && <p className={`${cardClass} text-sm text-slate-500`}>No one to call right now.</p>}
      {rows.map((r) => (
        <div key={r.appointment_id} className={`${cardClass} space-y-2 py-4!`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <Link to={`${base.patients}/${r.patient_id}`} className="font-medium text-slate-800 hover:underline">
                {r.patient_name}
              </Link>
              <a href={`tel:${r.phone}`} className="ml-2 text-sm text-brand-600">
                {r.phone}
              </a>
              <p className="text-xs text-slate-500">
                {r.doctor_name} advised a follow-up for {formatDate(r.follow_up_date)} (visit {formatDate(r.visit_date)}){r.nudged && ' | reminder sent'}
              </p>
            </div>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${r.overdue_days > 0 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-800'}`}>
              {r.overdue_days > 0 ? `${r.overdue_days} days overdue` : r.overdue_days === 0 ? 'Due today' : `Due in ${-r.overdue_days} days`}
            </span>
          </div>
          {r.last_call && (
            <p className="text-xs text-slate-500">
              Last call {formatDate(r.last_call.at)} {formatTime(r.last_call.at)}: {OUTCOMES.find(([v]) => v === r.last_call.outcome)?.[1]}
              {r.last_call.note && ` - ${r.last_call.note}`}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <input className={`${inputClass} w-56! py-1.5`} placeholder="Call note" value={notes[r.appointment_id] ?? ''} onChange={(e) => setNotes({ ...notes, [r.appointment_id]: e.target.value })} />
            {OUTCOMES.map(([v, l]) => (
              <button key={v} className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50" onClick={() => log(r, v)}>
                {l}
              </button>
            ))}
            <Link to={`${base.appointments}/new?patient_id=${r.patient_id}&doctor_id=${r.doctor_id}`} className="text-sm text-brand-600 hover:underline">
              Book now
            </Link>
          </div>
        </div>
      ))}
    </div>
  )
}

function Messages() {
  const [filters, setFilters] = useState({ patient_id: '', kind: '', status: '' })
  const [rows, setRows] = useState([])
  const [applied, setApplied] = useState(filters)

  useEffect(() => {
    listNotifications(Object.fromEntries(Object.entries(applied).filter(([, v]) => v))).then(setRows)
  }, [applied])

  return (
    <div className="space-y-3">
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setApplied(filters)
        }}
      >
        <input className={`${inputClass} w-40!`} placeholder="Patient ID" value={filters.patient_id} onChange={(e) => setFilters({ ...filters, patient_id: e.target.value })} />
        <select className={`${inputClass} w-44!`} value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })} aria-label="Kind">
          <option value="">All messages</option>
          {Object.entries(KINDS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select className={`${inputClass} w-40!`} value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} aria-label="Status">
          <option value="">Any status</option>
          {['scheduled', 'sent', 'failed', 'not_configured', 'cancelled'].map((s) => (
            <option key={s} value={s}>
              {STATUS_TEXT[s] ?? s}
            </option>
          ))}
        </select>
        <button className={secondaryButton}>Apply</button>
      </form>
      <div className={`${cardClass} overflow-x-auto p-0!`}>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              {['When', 'Patient', 'Message', 'Channel', 'Status'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((n) => (
              <tr key={n.id} className="align-top">
                <td className="px-3 py-2 whitespace-nowrap">
                  {formatDate(n.scheduled_at)} {formatTime(n.scheduled_at)}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{n.patient_id}</td>
                <td className="max-w-md px-3 py-2">
                  <span className="text-xs font-medium text-slate-500">{KINDS[n.kind] ?? n.kind}</span>
                  <span className="block truncate" title={n.text}>
                    {n.text}
                  </span>
                </td>
                <td className="px-3 py-2 capitalize">
                  {n.channel}
                  {n.language !== 'en' && <span className="text-xs text-slate-500"> ({n.language})</span>}
                </td>
                <td className={`px-3 py-2 ${STATUS_STYLE[n.status] ?? ''}`} title={n.error ?? ''}>
                  {STATUS_TEXT[n.status] ?? n.status}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                  No messages
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        &quot;Not set up&quot; means no WhatsApp or SMS provider is configured on the server yet; messages also appear in the patient app when the patient has an account.
      </p>
    </div>
  )
}

const PRESETS = [
  [7 * 24 * 60, '7 days before'],
  [3 * 24 * 60, '3 days before'],
  [2 * 24 * 60, '2 days before'],
  [24 * 60, '1 day before'],
  [6 * 60, '6 hours before'],
  [2 * 60, '2 hours before'],
  [60, '1 hour before'],
]

function Settings() {
  const [form, setForm] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    getReminderSettings().then(setForm)
  }, [])
  if (!form) return <p className="text-slate-500">Loading...</p>

  const toggle = (m) =>
    setForm({ ...form, offsets_minutes: form.offsets_minutes.includes(m) ? form.offsets_minutes.filter((x) => x !== m) : [...form.offsets_minutes, m] })
  const save = async () => {
    setMessage('')
    setError('')
    try {
      setForm(await saveReminderSettings(form))
      setMessage('Saved.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  return (
    <section className={`${cardClass} max-w-xl space-y-4`}>
      <div>
        <h2 className="text-sm font-semibold text-slate-800">Appointment reminders</h2>
        <p className="text-xs text-slate-500">Sent in the patient&apos;s language on the channels they chose, with confirm, change and cancel links.</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {PRESETS.map(([m, label]) => (
          <label key={m} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.offsets_minutes.includes(m)} onChange={() => toggle(m)} />
            {label}
          </label>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>
          <span className={labelClass}>Nudge an unbooked follow-up after (days)</span>
          <input type="number" min={0} max={30} className={inputClass} value={form.nudge_after_days} onChange={(e) => setForm({ ...form, nudge_after_days: Number(e.target.value) })} />
        </label>
        <label>
          <span className={labelClass}>Callback list: due within (days)</span>
          <input type="number" min={0} max={30} className={inputClass} value={form.callback_window_days} onChange={(e) => setForm({ ...form, callback_window_days: Number(e.target.value) })} />
        </label>
      </div>
      {message && <p className="text-sm text-accent-700">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button className={primaryButton} onClick={save}>
          Save
        </button>
        <button className={secondaryButton} onClick={() => runNotificationsNow().then((r) => setMessage(`Sent ${r.sent} due messages.`))}>
          Send due messages now
        </button>
      </div>
    </section>
  )
}

/** Front desk: who to call about follow-ups, what was sent, and (admins) the reminder schedule. */
export default function RemindersPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState('callbacks')
  const tabs = [
    ['callbacks', 'Callback list'],
    ['messages', 'Messages sent'],
    ...(user.role === ROLES.ADMIN ? [['settings', 'Reminder schedule']] : []),
  ]
  const base = { patients: PATIENT_BASE[user.role], appointments: APPOINTMENT_BASE[user.role] }
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Follow-ups and reminders</h1>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {tabs.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} className={`shrink-0 px-4 py-2 text-sm ${tab === key ? 'border-b-2 border-accent-600 font-medium text-brand-700' : 'text-slate-500'}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'callbacks' && <Callbacks base={base} />}
      {tab === 'messages' && <Messages />}
      {tab === 'settings' && <Settings />}
    </div>
  )
}
