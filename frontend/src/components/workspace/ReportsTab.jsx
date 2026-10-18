import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listReports } from '../../api/reports'
import { getApprovedSummaries } from '../../api/workspace'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE } from '../../routes/roles'
import Sparkline from '../reports/Sparkline'
import SummaryCard from '../reports/SummaryCard'
import { typeLabel } from '../reports/reportMeta'
import { SUMMARY_STATUS } from '../reports/summaryMeta'
import { cardClass, formatDate, primaryButton } from '../ui'

const STATUS_STYLE = {
  approved: 'bg-accent-100 text-accent-700',
  ready: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-700',
}

/** Trends from approved summaries: one row per test seen in at least two reports. */
function LabTrends({ patientId }) {
  const [series, setSeries] = useState(null)

  useEffect(() => {
    getApprovedSummaries(patientId)
      .then((summaries) => {
        const byKey = {}
        for (const s of summaries) {
          for (const t of s.tests) {
            if (t.value_numeric == null) continue
            ;(byKey[t.analyte_key] ??= { name: t.name, unit: t.unit, points: [] }).points.push({
              date: s.report_date,
              value: t.value_numeric,
              unit: t.unit,
              flag: t.flag,
            })
          }
        }
        setSeries(
          Object.values(byKey)
            .filter((x) => x.points.length > 1)
            .map((x) => ({ ...x, points: x.points.sort((a, b) => a.date.localeCompare(b.date)) })),
        )
      })
      .catch(() => setSeries([]))
  }, [patientId])

  if (!series?.length) return null
  return (
    <section className={cardClass}>
      <h2 className="mb-2 text-sm font-semibold text-slate-800">Lab trends (approved reports)</h2>
      <ul className="divide-y divide-slate-100">
        {series.map((s) => {
          const latest = s.points.at(-1)
          return (
            <li key={s.name} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="min-w-32 font-medium text-slate-800">{s.name}</span>
              <span className="text-xs text-slate-500">
                {s.points.map((p) => p.value).join(' -> ')} {s.unit}
              </span>
              <Sparkline points={s.points.map((p, i) => ({ ...p, current: i === s.points.length - 1 }))} />
              <span className="w-24 text-right text-xs text-slate-500">{formatDate(latest.date)}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default function ReportsTab({ appt, patient }) {
  const { user } = useAuth()
  const base = `${PATIENT_BASE[user.role]}/${patient.patient_id}/reports`
  const [reports, setReports] = useState(null)
  const [open, setOpen] = useState(null)

  useEffect(() => {
    listReports(patient.patient_id, { include_summary: true }).then(setReports).catch(() => setReports([]))
  }, [patient.patient_id])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">{reports?.length ?? '...'} report(s) on file</p>
        <Link to={`${base}/upload?appointment_id=${appt.id}`} className={primaryButton}>
          Upload report for this visit
        </Link>
      </div>

      <LabTrends patientId={patient.patient_id} />

      <section className={`${cardClass} p-0!`}>
        {reports?.length === 0 && <p className="p-5 text-sm text-slate-400">No reports yet.</p>}
        <ul className="divide-y divide-slate-100">
          {reports?.map((r) => (
            <li key={r.id} className="px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button className="text-left" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <span className="font-medium text-slate-800">{r.title || typeLabel(r.report_type)}</span>
                  <span className="ml-2 text-sm text-slate-500">
                    {typeLabel(r.report_type)} | {formatDate(r.report_date)}
                    {r.appointment_id === appt.id && ' | this visit'}
                  </span>
                </button>
                <span className="flex items-center gap-2 text-xs">
                  {r.summary?.critical_values.length > 0 && (
                    <span className="rounded bg-red-600 px-1.5 py-0.5 font-medium text-white">!! Critical</span>
                  )}
                  {r.summary?.abnormal_count > 0 && <span className="text-amber-800">{r.summary.abnormal_count} abnormal</span>}
                  <span className={`rounded-full px-2 py-0.5 ${STATUS_STYLE[r.summary?.status] ?? 'bg-slate-100 text-slate-600'}`}>
                    {r.summary ? SUMMARY_STATUS[r.summary.status] : 'Not summarised'}
                  </span>
                  <Link to={`${base}/${r.id}`} className="text-brand-600 hover:underline">
                    Open
                  </Link>
                </span>
              </div>
              {open === r.id && (
                <div className="mt-3">
                  <SummaryCard reportId={r.id} reviewPath={`${base}/${r.id}/summary`} />
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
