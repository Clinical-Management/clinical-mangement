import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { exportReceipts, getCollections, listApprovals, listDues, reconcile } from '../../api/billing'
import { MODES, rupees, toPaise } from '../../components/billing/money'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, primaryButton, secondaryButton, todayISO } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE } from '../../routes/roles'

const TABS = [
  ['day', 'Daily collection'],
  ['dues', 'Outstanding dues'],
  ['approvals', 'Waiting for approval'],
  ['export', 'Export'],
]

function download(blob, name) {
  const url = URL.createObjectURL(blob)
  Object.assign(document.createElement('a'), { href: url, download: name }).click()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}

function DailyCollection({ apptBase }) {
  const [day, setDay] = useState(todayISO())
  const [report, setReport] = useState(null)
  const [counted, setCounted] = useState({})
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getCollections(day).then(setReport)
  }, [day])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await reconcile({ date: day, counted: Object.fromEntries(Object.entries(counted).filter(([, v]) => v !== '').map(([k, v]) => [k, toPaise(v)])), note: note.trim() || null })
      setReport(await getCollections(day))
      setCounted({})
      setNote('')
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  if (!report) return <p className="text-slate-500">Loading...</p>
  const recon = report.reconciliation
  return (
    <div className="space-y-5">
      <input type="date" className={`${inputClass} w-auto!`} value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" />
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ['Received', report.received],
          ['Refunded', report.refunded],
          ['Net collection', report.net],
          ['Receipts', null, report.receipt_count],
        ].map(([label, paise, count]) => (
          <div key={label} className={cardClass}>
            <p className="text-xs text-slate-500">{label}</p>
            <p className="text-2xl font-semibold text-slate-800">{paise === null ? count : rupees(paise)}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">By payment mode</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-1 font-medium">Mode</th>
                <th className="py-1 text-right font-medium">Received</th>
                <th className="py-1 text-right font-medium">Refunded</th>
                <th className="py-1 text-right font-medium">Net</th>
              </tr>
            </thead>
            <tbody>
              {report.by_mode.map((m) => (
                <tr key={m.mode} className="border-t border-slate-100">
                  <td className="py-1.5 capitalize">{m.mode}</td>
                  <td className="py-1.5 text-right">{rupees(m.received)}</td>
                  <td className="py-1.5 text-right">{rupees(m.refunded)}</td>
                  <td className="py-1.5 text-right font-medium">{rupees(m.net)}</td>
                </tr>
              ))}
              {!report.by_mode.length && (
                <tr>
                  <td colSpan={4} className="py-3 text-center text-slate-500">
                    No payments on this day
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        <section className={cardClass}>
          <h2 className="mb-1 text-sm font-semibold text-slate-800">End-of-day reconciliation</h2>
          <p className="mb-3 text-xs text-slate-500">Enter the cash counted in the drawer and the UPI / card settlement amounts.</p>
          {recon && (
            <div className={`mb-3 rounded-md px-3 py-2 text-sm ${recon.variance === 0 ? 'bg-accent-50 text-accent-700' : 'bg-amber-50 text-amber-900'}`}>
              Last reconciled {formatTime(recon.at)} by {recon.by_role}:{' '}
              {recon.variance === 0 ? 'matches the receipts.' : `${recon.variance > 0 ? 'over' : 'short'} by ${rupees(Math.abs(recon.variance))}.`}
              {recon.note && <span className="block text-xs">{recon.note}</span>}
            </div>
          )}
          <form onSubmit={submit} className="space-y-2">
            {MODES.map(([mode, label]) => {
              const expected = report.by_mode.find((m) => m.mode === mode)?.net ?? 0
              return (
                <label key={mode} className="flex items-center gap-3 text-sm">
                  <span className="w-16">{label}</span>
                  <input className={`${inputClass} w-32! py-1.5`} inputMode="decimal" placeholder={String(expected / 100)} value={counted[mode] ?? ''} onChange={(e) => setCounted({ ...counted, [mode]: e.target.value })} />
                  <span className="text-xs text-slate-500">expected {rupees(expected)}</span>
                </label>
              )
            })}
            <input className={inputClass} placeholder="Note (e.g. reason for a difference)" value={note} onChange={(e) => setNote(e.target.value)} />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button className={primaryButton}>Save reconciliation</button>
          </form>
        </section>
      </div>

      <section className={`${cardClass} overflow-x-auto p-0!`}>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              {['Receipt', 'Time', 'Patient', 'Mode', 'Amount', 'Balance after', 'By'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {report.receipts.map((r) => (
              <tr key={r.id}>
                <td className="px-3 py-2 font-mono text-xs">
                  <Link to={`${apptBase}/${r.appointment_id}`} className="text-brand-700 hover:underline">
                    {r.number}
                  </Link>
                </td>
                <td className="px-3 py-2">{formatTime(r.issued_at)}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.patient_id}</td>
                <td className="px-3 py-2 capitalize">{r.mode}</td>
                <td className={`px-3 py-2 ${r.kind === 'refund' ? 'text-red-700' : ''}`}>
                  {r.kind === 'refund' && '- '}
                  {rupees(r.amount)}
                </td>
                <td className="px-3 py-2">{rupees(r.balance)}</td>
                <td className="px-3 py-2 capitalize">{r.issued_by_role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

function Dues({ apptBase }) {
  const [dues, setDues] = useState(null)
  useEffect(() => {
    listDues().then(setDues)
  }, [])
  if (!dues) return <p className="text-slate-500">Loading...</p>
  const total = dues.reduce((s, d) => s + d.balance, 0)
  return (
    <section className={`${cardClass} overflow-x-auto p-0!`}>
      <p className="px-4 py-3 text-sm text-slate-600">
        {dues.length} bills, {rupees(total)} outstanding
      </p>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            {['Visit', 'Patient', 'Phone', 'Doctor', 'Total', 'Due', ''].map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {dues.map((d) => (
            <tr key={d.appointment_id}>
              <td className="px-3 py-2">{formatDate(d.date)}</td>
              <td className="px-3 py-2">
                {d.patient_name}
                <span className="block font-mono text-xs text-slate-500">{d.patient_id}</span>
              </td>
              <td className="px-3 py-2">{d.phone}</td>
              <td className="px-3 py-2">{d.doctor_name}</td>
              <td className="px-3 py-2">{rupees(d.total)}</td>
              <td className="px-3 py-2 font-medium text-amber-800">{rupees(d.balance)}</td>
              <td className="px-3 py-2 text-right">
                <Link to={`${apptBase}/${d.appointment_id}`} className="text-brand-600 hover:underline">
                  Collect
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Approvals({ apptBase }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    listApprovals().then(setData)
  }, [])
  if (!data) return <p className="text-slate-500">Loading...</p>
  const rows = [
    ...data.concessions.map((c) => ({ ...c, what: `Concession: ${c.type}${c.percent != null ? ` ${c.percent}%` : c.amount ? ` ${rupees(c.amount)}` : ''}`, key: `c${c.appointment_id}` })),
    ...data.refunds.map((r) => ({ ...r, what: `Refund ${rupees(r.amount)} by ${r.mode}`, key: `r${r.id}` })),
  ]
  if (!rows.length) return <p className="text-sm text-slate-500">Nothing is waiting for approval.</p>
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.key} className={`${cardClass} flex flex-wrap items-center justify-between gap-2 py-3!`}>
          <span className="text-sm">
            <b>{r.what}</b> - {r.reason || 'no reason'}
            <span className="block text-xs text-slate-500">
              {r.patient_id} | visit {formatDate(r.date)} | asked by {r.requested_by_role}
            </span>
          </span>
          <Link to={`${apptBase}/${r.appointment_id}`} className="text-sm text-brand-600 hover:underline">
            Open bill
          </Link>
        </li>
      ))}
    </ul>
  )
}

function Export() {
  const [range, setRange] = useState({ date_from: todayISO().slice(0, 8) + '01', date_to: todayISO() })
  const [error, setError] = useState('')
  return (
    <section className={`${cardClass} space-y-3`}>
      <p className="text-sm text-slate-600">Download receipts and refunds as CSV for your accountant (opens in Excel; imports into Tally or Zoho Books).</p>
      <div className="flex flex-wrap items-center gap-2">
        <input type="date" className={`${inputClass} w-auto!`} value={range.date_from} onChange={(e) => setRange({ ...range, date_from: e.target.value })} aria-label="From" />
        <span className="text-slate-500">to</span>
        <input type="date" className={`${inputClass} w-auto!`} value={range.date_to} onChange={(e) => setRange({ ...range, date_to: e.target.value })} aria-label="To" />
        <button
          className={secondaryButton}
          onClick={() =>
            exportReceipts(range)
              .then((blob) => download(blob, `receipts-${range.date_from}-to-${range.date_to}.csv`))
              .catch((err) => setError(errorMessage(err, 'Could not export')))
          }
        >
          Download CSV
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  )
}

/** Front desk billing: the day's collection and reconciliation, dues, approvals and exports. */
export default function BillingPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState('day')
  const apptBase = APPOINTMENT_BASE[user.role]
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Billing</h1>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} className={`shrink-0 px-4 py-2 text-sm ${tab === key ? 'border-b-2 border-accent-600 font-medium text-brand-700' : 'text-slate-500'}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'day' && <DailyCollection apptBase={apptBase} />}
      {tab === 'dues' && <Dues apptBase={apptBase} />}
      {tab === 'approvals' && <Approvals apptBase={apptBase} />}
      {tab === 'export' && <Export />}
    </div>
  )
}
