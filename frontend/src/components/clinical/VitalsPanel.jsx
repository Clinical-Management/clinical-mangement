import { useEffect, useState } from 'react'
import { listVisitVitals, recordVitals } from '../../api/clinical'
import { cardClass, errorMessage, formatTime, inputClass, labelClass, primaryButton, secondaryButton } from '../ui'
import { FLAG_META, formatReading, readingFlag, VITALS } from './vitalsMeta'

const EMPTY = {
  bp_systolic: '', bp_diastolic: '', pulse: '', temperature: '', temperature_unit: 'F',
  spo2: '', weight_kg: '', height_cm: '', note: '',
}

const toNumber = (v) => (v === '' ? null : Number(v))

function Reading({ label, value, unit, flag }) {
  const meta = flag && FLAG_META[flag]
  return (
    <div className={`rounded-lg border px-3 py-2 ${meta ? (flag.startsWith('critical') ? 'border-red-300 bg-red-50' : 'border-amber-300 bg-amber-50') : 'border-slate-200'}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-lg font-semibold text-slate-800">
        {value ?? '-'} <span className="text-xs font-normal text-slate-500">{value != null && unit}</span>
      </p>
      {meta && (
        <p className={`text-xs font-medium ${meta.text}`}>
          {meta.icon} {meta.label}
        </p>
      )}
    </div>
  )
}

/** Vitals for one visit: latest readings with abnormal values highlighted, and the entry form. */
export default function VitalsPanel({ appt, canRecord }) {
  const [readings, setReadings] = useState([])
  const [form, setForm] = useState(null) // null = closed
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    listVisitVitals(appt.id).then(setReadings).catch(() => setReadings([]))
  }, [appt.id])

  const latest = readings.at(-1)
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const weight = toNumber(form?.weight_kg)
  const height = toNumber(form?.height_cm)
  const bmiPreview = weight && height ? (weight / (height / 100) ** 2).toFixed(1) : null

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { temperature_unit, note, ...readings } = form
      const payload = {
        ...Object.fromEntries(Object.entries(readings).map(([k, v]) => [k, toNumber(v)])),
        temperature_unit,
        note: note.trim() || null,
      }
      const saved = await recordVitals(appt.id, payload)
      setReadings((list) => [...list, saved])
      setForm(null)
    } catch (err) {
      setError(errorMessage(err, 'Could not save vitals'))
    } finally {
      setSaving(false)
    }
  }

  const field = (key, label, props = {}) => (
    <label>
      <span className={labelClass}>{label}</span>
      <input type="number" inputMode="decimal" step="any" className={inputClass} value={form[key]} onChange={set(key)} {...props} />
    </label>
  )

  return (
    <section className={cardClass}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-800">
          Vitals
          {latest && (
            <span className="ml-2 font-normal text-slate-500">
              recorded {formatTime(latest.recorded_at)} by {latest.recorded_by_role}
              {readings.length > 1 && ` (${readings.length} readings this visit)`}
            </span>
          )}
        </h2>
        {canRecord && !form && (
          <button className={latest ? secondaryButton : primaryButton} onClick={() => setForm(EMPTY)}>
            {latest ? 'Record again' : 'Record vitals'}
          </button>
        )}
      </div>

      {latest ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {VITALS.map((v) => (
            <Reading
              key={v.key}
              label={v.label}
              unit={v.unit}
              value={formatReading(latest, v.key)}
              flag={readingFlag(latest, v.key)}
            />
          ))}
        </div>
      ) : (
        !form && <p className="text-sm text-slate-400">No vitals recorded for this visit.</p>
      )}
      {latest?.height_carried_forward && (
        <p className="mt-2 text-xs text-slate-500">BMI uses the height recorded at an earlier visit.</p>
      )}
      {latest?.note && <p className="mt-2 text-sm text-slate-600">Note: {latest.note}</p>}

      {form && (
        <form onSubmit={save} className="mt-4 space-y-4 border-t border-slate-100 pt-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {field('bp_systolic', 'BP systolic (mmHg)', { placeholder: '120' })}
            {field('bp_diastolic', 'BP diastolic (mmHg)', { placeholder: '80' })}
            {field('pulse', 'Pulse (bpm)')}
            {field('spo2', 'SpO2 (%)')}
            <label>
              <span className={labelClass}>Temperature</span>
              <div className="flex">
                <input type="number" step="0.1" inputMode="decimal" className={`${inputClass} rounded-r-none`} value={form.temperature} onChange={set('temperature')} />
                <select className="rounded-r-md border border-l-0 border-slate-300 bg-slate-50 px-2 text-sm" value={form.temperature_unit} onChange={set('temperature_unit')}>
                  <option value="F">°F</option>
                  <option value="C">°C</option>
                </select>
              </div>
            </label>
            {field('weight_kg', 'Weight (kg)')}
            {field('height_cm', 'Height (cm)')}
            <div>
              <span className={labelClass}>BMI</span>
              <p className="py-2 text-sm text-slate-700">{bmiPreview ?? (weight ? 'uses last height' : '-')}</p>
            </div>
          </div>
          <label className="block">
            <span className={labelClass}>Note</span>
            <input className={inputClass} placeholder="e.g. BP taken after rest, left arm" value={form.note} onChange={set('note')} />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" className={secondaryButton} onClick={() => setForm(null)}>
              Cancel
            </button>
            <button className={primaryButton} disabled={saving}>
              {saving ? 'Saving...' : 'Save vitals'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
