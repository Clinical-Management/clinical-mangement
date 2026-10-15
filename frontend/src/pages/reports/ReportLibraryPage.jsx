import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { listAppointments } from '../../api/appointments'
import { getPatient } from '../../api/patients'
import { exportReports, listReports } from '../../api/reports'
import { KIND_LABEL, REPORT_TYPES, saveOrShare, typeLabel } from '../../components/reports/reportMeta'
import { cardClass, errorBox, errorMessage, formatDate, formatDay, inputClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE, ROLES } from '../../routes/roles'

function ReportItem({ report, base, selectable, selected, onToggle }) {
  const v = report.versions.at(-1)
  return (
    <div className="flex items-center gap-3">
      {selectable && <input type="checkbox" checked={selected} onChange={onToggle} aria-label={`Select ${report.title ?? report.report_type}`} />}
      <Link to={`${base}/${report.id}`} className="min-w-0 flex-1 hover:underline">
        <span className="font-medium text-slate-800">{report.title || typeLabel(report.report_type)}</span>
        <span className="ml-2 text-sm text-slate-500">
          {typeLabel(report.report_type)} | {report.ordering_doctor} | {KIND_LABEL[v.kind]}
          {report.current_version > 1 && ` | v${report.current_version}`}
        </span>
      </Link>
      {v.warnings.length > 0 && <span className="text-xs text-amber-700" title={v.warnings.join(' ')}>⚠ quality</span>}
    </div>
  )
}

export default function ReportLibraryPage() {
  const { patientId } = useParams()
  const [params] = useSearchParams()
  const { user } = useAuth()
  const base = `${PATIENT_BASE[user.role]}/${patientId}/reports`
  const canExport = user.role !== ROLES.RECEPTIONIST

  const [patient, setPatient] = useState(null)
  const [visits, setVisits] = useState([])
  const [reports, setReports] = useState(null)
  const [filters, setFilters] = useState({
    report_type: '',
    date_from: '',
    date_to: '',
    appointment_id: params.get('appointment_id') ?? '',
  })
  const [view, setView] = useState('timeline')
  const [selected, setSelected] = useState(new Set())
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    getPatient(patientId).then(setPatient).catch(() => {})
    listAppointments({ patient_id: patientId }).then(setVisits).catch(() => {})
  }, [patientId])

  useEffect(() => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    listReports(patientId, params)
      .then((list) => {
        setReports(list)
        setError('')
      })
      .catch((err) => setError(errorMessage(err, 'Could not load reports')))
  }, [patientId, filters])

  const toggle = (id) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const exportSelected = async (share) => {
    setExporting(true)
    try {
      const blob = await exportReports(patientId, [...selected])
      await saveOrShare(blob, `${patientId}-reports.pdf`, share)
    } catch (err) {
      setError(errorMessage(err, 'Export failed'))
    } finally {
      setExporting(false)
    }
  }

  // Timeline: grouped by month of the report date
  const groups = (reports ?? []).reduce((acc, r) => {
    const key = r.report_date.slice(0, 7)
    ;(acc[key] ??= []).push(r)
    return acc
  }, {})
  const set = (key) => (e) => setFilters({ ...filters, [key]: e.target.value })

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">Reports</h1>
          {patient && (
            <p className="text-sm text-slate-500">
              <Link to={`${PATIENT_BASE[user.role]}/${patientId}`} className="text-brand-600 hover:underline">
                {patient.full_name}
              </Link>{' '}
              ({patient.patient_id})
            </p>
          )}
        </div>
        <Link to={`${base}/upload`} className={primaryButton}>
          Upload report
        </Link>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <select className={`${inputClass} w-auto!`} value={filters.report_type} onChange={set('report_type')} aria-label="Report type">
          <option value="">All types</option>
          {REPORT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <label className="text-xs text-slate-500">
          From
          <input type="date" className={`${inputClass} w-auto!`} value={filters.date_from} onChange={set('date_from')} />
        </label>
        <label className="text-xs text-slate-500">
          To
          <input type="date" className={`${inputClass} w-auto!`} value={filters.date_to} onChange={set('date_to')} />
        </label>
        <select className={`${inputClass} w-auto!`} value={filters.appointment_id} onChange={set('appointment_id')} aria-label="Visit">
          <option value="">All visits</option>
          {visits.map((v) => (
            <option key={v.id} value={v.id}>
              {formatDay(v.date)} with {v.doctor_name}
            </option>
          ))}
        </select>
        <div className="ml-auto inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-sm">
          {['timeline', 'list'].map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded px-3 py-1 capitalize ${view === v ? 'bg-brand-gradient text-white' : 'text-slate-600'}`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {canExport && selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-brand-50 px-4 py-2 text-sm text-brand-800">
          {selected.size} selected
          <button className={`${primaryButton} px-3 py-1`} disabled={exporting} onClick={() => exportSelected(false)}>
            Export PDF
          </button>
          <button className={`${secondaryButton} px-3 py-1`} disabled={exporting} onClick={() => exportSelected(true)}>
            Share PDF
          </button>
          <button className="text-brand-600 hover:underline" onClick={() => setSelected(new Set())}>
            Clear
          </button>
        </div>
      )}

      {error && <p className={errorBox}>{error}</p>}

      <section className={cardClass}>
        {!reports ? (
          <p className="text-sm text-slate-500">Loading...</p>
        ) : reports.length === 0 ? (
          <p className="text-sm text-slate-400">No reports match.</p>
        ) : view === 'list' ? (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                {canExport && <th className="w-8 py-2" />}
                <th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Title</th>
                <th className="py-2 pr-4">Ordered by</th>
                <th className="py-2 pr-4">Visit</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} className="border-b border-slate-100">
                  {canExport && (
                    <td className="py-2">
                      <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label="Select" />
                    </td>
                  )}
                  <td className="py-2 pr-4 text-slate-600">{formatDate(r.report_date)}</td>
                  <td className="py-2 pr-4">{typeLabel(r.report_type)}</td>
                  <td className="py-2 pr-4">
                    <Link to={`${base}/${r.id}`} className="font-medium text-brand-700 hover:underline">
                      {r.title || typeLabel(r.report_type)}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 text-slate-600">{r.ordering_doctor}</td>
                  <td className="py-2 pr-4 text-slate-600">{r.visit_date ? formatDate(r.visit_date) : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <ol className="relative ml-2 border-l-2 border-brand-100">
            {Object.entries(groups).map(([month, items]) => (
              <li key={month} className="mb-6 ml-5">
                <span className="absolute -left-[7px] mt-1 h-3 w-3 rounded-full bg-brand-gradient" />
                <h3 className="mb-2 text-sm font-semibold text-slate-700">
                  {new Date(`${month}-01T00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                </h3>
                <ul className="space-y-2">
                  {items.map((r) => (
                    <li key={r.id} className="rounded-lg border border-slate-200 px-3 py-2">
                      <p className="mb-0.5 text-xs text-slate-500">{formatDate(r.report_date)}</p>
                      <ReportItem
                        report={r}
                        base={base}
                        selectable={canExport}
                        selected={selected.has(r.id)}
                        onToggle={() => toggle(r.id)}
                      />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}
