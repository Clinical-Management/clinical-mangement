import { useEffect, useState } from 'react'
import { getVitalsTrend } from '../../api/clinical'
import LineChart from '../charts/LineChart'
import { cardClass, errorMessage, formatDate } from '../ui'
import { FLAG_META, formatReading, readingFlag, SERIES_COLORS, VITALS } from './vitalsMeta'

// One chart per measure (small multiples): different units never share an axis.
const CHARTS = [
  { title: 'Blood pressure', unit: 'mmHg', series: [['bp_systolic', 'Systolic'], ['bp_diastolic', 'Diastolic']] },
  { title: 'Pulse', unit: 'bpm', series: [['pulse', 'Pulse']] },
  { title: 'Temperature', unit: '°C', series: [['temperature_c', 'Temperature']] },
  { title: 'SpO2', unit: '%', series: [['spo2', 'SpO2']] },
  { title: 'Weight', unit: 'kg', series: [['weight_kg', 'Weight']] },
  { title: 'BMI', unit: 'kg/m²', series: [['bmi', 'BMI']] },
]

function FlagText({ flag }) {
  if (!flag) return null
  const meta = FLAG_META[flag]
  return (
    <span className={`ml-1 text-xs ${meta.text}`}>
      {meta.icon} {meta.label}
    </span>
  )
}

export default function VitalsTrends({ patientId }) {
  const [trend, setTrend] = useState(null)
  const [error, setError] = useState('')
  const [showTable, setShowTable] = useState(false)

  useEffect(() => {
    getVitalsTrend(patientId)
      .then(setTrend)
      .catch((err) => setError(errorMessage(err, 'Could not load vitals')))
  }, [patientId])

  if (error) return <p className="text-sm text-red-600">{error}</p>
  if (!trend) return null

  const readings = trend.readings.map((r) => ({ ...r, t: new Date(r.recorded_at) }))

  return (
    <section className={cardClass}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-800">Vitals trends</h2>
        {readings.length > 0 && (
          <button className="text-sm text-brand-600 hover:underline" onClick={() => setShowTable(!showTable)}>
            {showTable ? 'Show charts' : 'Show table'}
          </button>
        )}
      </div>
      {trend.paediatric && (
        <p className="mb-3 text-xs text-slate-500">
          Child: only temperature and SpO2 are flagged; BP, pulse and BMI need age-specific charts.
        </p>
      )}

      {readings.length === 0 ? (
        <p className="text-sm text-slate-400">No vitals recorded yet.</p>
      ) : showTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-4">Date</th>
                {VITALS.map((v) => (
                  <th key={v.key} className="py-2 pr-4">
                    {v.label} <span className="normal-case">({v.unit})</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...readings].reverse().map((r) => (
                <tr key={r.id} className="border-b border-slate-100">
                  <td className="py-2 pr-4 text-slate-600">{formatDate(r.recorded_at)}</td>
                  {VITALS.map((v) => (
                    <td key={v.key} className="py-2 pr-4 text-slate-800">
                      {formatReading(r, v.key) ?? '-'}
                      <FlagText flag={readingFlag(r, v.key)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {CHARTS.map((chart) => {
            const series = chart.series
              .map(([key, label], i) => ({
                label,
                color: SERIES_COLORS[i],
                points: readings.filter((r) => r[key] != null).map((r) => ({ t: r.t, v: r[key], flag: r.flags[key] })),
              }))
              .filter((s) => s.points.length)
            if (!series.length) return null
            const band = trend.ranges[chart.series[0][0]]
            return (
              <div key={chart.title}>
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-slate-700">
                    {chart.title} <span className="font-normal text-slate-500">({chart.unit})</span>
                  </h3>
                  {series.length > 1 && (
                    <span className="flex gap-3 text-xs text-slate-600">
                      {series.map((s) => (
                        <span key={s.label} className="flex items-center gap-1">
                          <span className="inline-block h-0.5 w-3" style={{ background: s.color }} />
                          {s.label}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                <LineChart series={series} band={chart.series.length === 1 ? band : null} unit={chart.unit} ariaLabel={`${chart.title} over time`} />
              </div>
            )
          })}
        </div>
      )}
      {!showTable && readings.length > 0 && (
        <p className="mt-2 text-xs text-slate-400">Shaded band: normal range. Ringed points are outside it.</p>
      )}
    </section>
  )
}
