import { useEffect, useState } from 'react'
import { exportAudit, listAudit, staffActivity, verifyAudit } from '../../api/admin'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, secondaryButton } from '../../components/ui'

const ACTIONS = ['view', 'create', 'update', 'delete', 'denied', 'login', 'login_failed', 'logout', 'mfa_failed', 'mfa_enabled', 'mfa_reset', 'password_reset', 'fee_override', 'refund', 'discount_approved']
const PAGE = 100
const EMPTY = { patient_id: '', action: '', date_from: '', date_to: '' }

const ACTION_STYLE = { denied: 'text-red-700', login_failed: 'text-red-700', mfa_failed: 'text-red-700', delete: 'text-red-700' }

/** Who viewed or changed what. Entries are signed and numbered, so edits or deletions show up in the check. */
export default function AuditLogPage() {
  const [tab, setTab] = useState('log')
  const [filters, setFilters] = useState(EMPTY)
  const [applied, setApplied] = useState(EMPTY)
  const [entries, setEntries] = useState([])
  const [page, setPage] = useState(0)
  const [activity, setActivity] = useState([])
  const [check, setCheck] = useState(null)
  const [error, setError] = useState('')

  const params = Object.fromEntries(Object.entries(applied).filter(([, v]) => v))

  useEffect(() => {
    const p = Object.fromEntries(Object.entries(applied).filter(([, v]) => v))
    if (tab === 'log') listAudit({ ...p, limit: PAGE, skip: page * PAGE }).then(setEntries).catch((err) => setError(errorMessage(err, 'Could not load')))
    else staffActivity({ date_from: p.date_from, date_to: p.date_to }).then(setActivity)
  }, [applied, page, tab])

  const download = async () => {
    const url = URL.createObjectURL(await exportAudit(params))
    Object.assign(document.createElement('a'), { href: url, download: 'audit-log.csv' }).click()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-800">Audit log</h1>
        <div className="flex gap-2">
          <button className={secondaryButton} onClick={() => verifyAudit().then(setCheck)}>
            Check integrity
          </button>
          <button className={secondaryButton} onClick={download}>
            Export CSV
          </button>
        </div>
      </div>
      {check && (
        <div className={`rounded-md px-4 py-3 text-sm ${check.ok ? 'bg-accent-50 text-accent-700' : 'bg-red-50 text-red-700'}`}>
          {check.ok ? `✓ All ${check.checked} entries are intact.` : `Problems found in ${check.checked} entries:`}
          {!check.ok && (
            <ul className="mt-1 list-disc pl-5">
              {check.problems.map((p, i) => (
                <li key={i}>
                  #{p.seq}: {p.issue}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-1 border-b border-slate-200">
        {[
          ['log', 'Entries'],
          ['activity', 'Staff activity'],
        ].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} className={`px-4 py-2 text-sm ${tab === key ? 'border-b-2 border-accent-600 font-medium text-brand-700' : 'text-slate-500'}`}>
            {label}
          </button>
        ))}
      </div>

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setPage(0)
          setApplied(filters)
        }}
      >
        {tab === 'log' && (
          <>
            <input className={`${inputClass} w-40!`} placeholder="Patient ID" value={filters.patient_id} onChange={(e) => setFilters({ ...filters, patient_id: e.target.value })} />
            <select className={`${inputClass} w-44!`} value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} aria-label="Action">
              <option value="">All actions</option>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </>
        )}
        <input type="date" className={`${inputClass} w-auto!`} value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} aria-label="From" />
        <input type="date" className={`${inputClass} w-auto!`} value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} aria-label="To" />
        <button className={secondaryButton}>Apply</button>
      </form>

      {tab === 'log' ? (
        <div className={`${cardClass} overflow-x-auto p-0!`}>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                {['#', 'When', 'Who', 'Action', 'Record', 'Patient', 'Result'].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="px-3 py-2 text-slate-400">{e.seq}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {formatDate(e.at)} {formatTime(e.at)}
                  </td>
                  <td className="px-3 py-2">
                    {e.actor_name ?? (e.details?.email || '-')}
                    <span className="block text-xs text-slate-500">{e.actor_role}</span>
                  </td>
                  <td className={`px-3 py-2 font-medium ${ACTION_STYLE[e.action] ?? 'text-slate-700'}`}>{e.action.replace(/_/g, ' ')}</td>
                  <td className="max-w-xs truncate px-3 py-2 font-mono text-xs" title={e.path ?? ''}>
                    {e.path ?? `${e.resource}${e.resource_id ? `/${e.resource_id}` : ''}`}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{e.patient_id ?? ''}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">{e.status ?? (Object.keys(e.details ?? {}).length ? JSON.stringify(e.details) : '')}</td>
                </tr>
              ))}
              {!entries.length && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                    No entries
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="flex justify-between border-t border-slate-100 px-3 py-2 text-sm">
            <button className="text-brand-600 disabled:text-slate-300" disabled={!page} onClick={() => setPage(page - 1)}>
              Newer
            </button>
            <button className="text-brand-600 disabled:text-slate-300" disabled={entries.length < PAGE} onClick={() => setPage(page + 1)}>
              Older
            </button>
          </div>
        </div>
      ) : (
        <div className={`${cardClass} overflow-x-auto p-0!`}>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                {['Staff member', 'Role', 'Views', 'Changes', 'Denied', 'Last active'].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {activity.map((a) => (
                <tr key={a.actor_id}>
                  <td className="px-3 py-2">
                    {a.name}
                    <span className="block text-xs text-slate-500">{a.email}</span>
                  </td>
                  <td className="px-3 py-2 capitalize">{a.role}</td>
                  <td className="px-3 py-2">{a.counts.view ?? 0}</td>
                  <td className="px-3 py-2">{(a.counts.create ?? 0) + (a.counts.update ?? 0) + (a.counts.delete ?? 0)}</td>
                  <td className={`px-3 py-2 ${a.counts.denied ? 'font-medium text-red-700' : ''}`}>{a.counts.denied ?? 0}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {formatDate(a.last_active)} {formatTime(a.last_active)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
