import { useState } from 'react'
import { updateMedical } from '../../api/patients'
import { cardClass, errorMessage, formatDate, inputClass, primaryButton, secondaryButton } from '../ui'
import { labelOf, SEVERITIES } from './options'

const SECTIONS = [
  {
    key: 'allergies',
    title: 'Allergies',
    empty: 'No known allergies',
    fields: [
      { key: 'substance', label: 'Substance', required: true },
      { key: 'reaction', label: 'Reaction' },
      { key: 'severity', label: 'Severity', options: SEVERITIES },
    ],
    summary: (a) => [a.reaction, a.severity && labelOf(SEVERITIES, a.severity)].filter(Boolean).join(' | '),
    titleOf: (a) => a.substance,
  },
  {
    key: 'chronic_conditions',
    title: 'Chronic conditions',
    empty: 'None recorded',
    fields: [
      { key: 'name', label: 'Condition', required: true },
      { key: 'since_year', label: 'Since (year)', type: 'number' },
      { key: 'notes', label: 'Notes' },
    ],
    summary: (c) => [c.since_year && `since ${c.since_year}`, c.notes].filter(Boolean).join(' | '),
    titleOf: (c) => c.name,
  },
  {
    key: 'current_medications',
    title: 'Current medicines',
    empty: 'None recorded',
    fields: [
      { key: 'name', label: 'Medicine', required: true },
      { key: 'dosage', label: 'Dosage' },
      { key: 'frequency', label: 'Frequency' },
      { key: 'notes', label: 'Notes' },
    ],
    summary: (m) => [m.dosage, m.frequency, m.notes].filter(Boolean).join(' | '),
    titleOf: (m) => m.name,
  },
]

const SEVERITY_STYLE = {
  severe: 'border-red-200 bg-red-50 text-red-800',
  moderate: 'border-amber-200 bg-amber-50 text-amber-800',
}

function ItemsView({ section, items }) {
  if (!items.length) return <p className="text-sm text-slate-400">{section.empty}</p>
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li
          key={i}
          className={`rounded-md border px-3 py-2 text-sm ${
            SEVERITY_STYLE[item.severity] ?? 'border-slate-200 bg-slate-50 text-slate-800'
          }`}
        >
          <span className="font-medium">{section.titleOf(item)}</span>
          {section.summary(item) && <span className="ml-2 opacity-75">{section.summary(item)}</span>}
        </li>
      ))}
    </ul>
  )
}

function ItemsEditor({ section, items, onChange }) {
  const update = (i, key, value) => onChange(items.map((it, j) => (j === i ? { ...it, [key]: value } : it)))
  const blank = Object.fromEntries(section.fields.map((f) => [f.key, '']))

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2 rounded-md border border-slate-200 p-2">
          {section.fields.map((f) => (
            <label key={f.key} className="min-w-28 flex-1">
              <span className="mb-0.5 block text-xs text-slate-500">{f.label}</span>
              {f.options ? (
                <select className={inputClass} value={item[f.key] ?? ''} onChange={(e) => update(i, f.key, e.target.value)}>
                  <option value="">-</option>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className={inputClass}
                  type={f.type ?? 'text'}
                  required={f.required}
                  value={item[f.key] ?? ''}
                  onChange={(e) => update(i, f.key, e.target.value)}
                />
              )}
            </label>
          ))}
          <button
            type="button"
            onClick={() => onChange(items.filter((_, j) => j !== i))}
            className="px-2 py-2 text-sm text-red-600 hover:underline"
          >
            Remove
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...items, blank])} className="text-sm text-brand-600 hover:underline">
        + Add
      </button>
    </div>
  )
}

// Blank strings -> null, numeric fields -> numbers
const clean = (medical) =>
  Object.fromEntries(
    SECTIONS.map((s) => [
      s.key,
      medical[s.key].map((item) =>
        Object.fromEntries(
          s.fields.map((f) => {
            const v = item[f.key]
            if (v === '' || v == null) return [f.key, null]
            return [f.key, f.type === 'number' ? Number(v) : v]
          }),
        ),
      ),
    ]),
  )

export default function MedicalInfoPanel({ patient, onUpdated }) {
  const [draft, setDraft] = useState(null) // null = view mode
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      onUpdated(await updateMedical(patient.patient_id, clean(draft)))
      setDraft(null)
    } catch (err) {
      setError(errorMessage(err, 'Could not save medical information'))
    } finally {
      setSaving(false)
    }
  }

  const medical = draft ?? patient.medical

  return (
    <form onSubmit={save} className={cardClass}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">Medical information</h2>
        {!draft && (
          <button type="button" className="text-sm text-brand-600 hover:underline" onClick={() => setDraft(patient.medical)}>
            Edit
          </button>
        )}
      </div>

      <div className="space-y-5">
        {SECTIONS.map((s) => (
          <div key={s.key}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{s.title}</h3>
            {draft ? (
              <ItemsEditor section={s} items={medical[s.key]} onChange={(items) => setDraft({ ...draft, [s.key]: items })} />
            ) : (
              <ItemsView section={s} items={medical[s.key]} />
            )}
          </div>
        ))}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-slate-400">
          {patient.medical_updated_at
            ? `Last updated ${formatDate(patient.medical_updated_at)} by ${patient.medical_updated_by_role}`
            : 'Not yet updated'}
        </span>
        {draft && (
          <div className="flex gap-2">
            <button type="button" className={secondaryButton} onClick={() => setDraft(null)}>
              Cancel
            </button>
            <button className={primaryButton} disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        )}
      </div>
    </form>
  )
}
