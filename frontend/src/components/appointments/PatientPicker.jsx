import { useEffect, useState } from 'react'
import { listPatients } from '../../api/patients'
import { useAuth } from '../../context/AuthContext'
import { ROLES } from '../../routes/roles'
import { inputClass, secondaryButton } from '../ui'

/** Patients choose among their own family profiles; staff search all patients. */
export default function PatientPicker({ value, onChange }) {
  const { user } = useAuth()
  const isOwner = user.role === ROLES.PATIENT
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [searched, setSearched] = useState(false)

  useEffect(() => {
    if (isOwner) listPatients().then(setResults)
  }, [isOwner])

  if (isOwner) {
    return (
      <select
        className={inputClass}
        required
        value={value?.patient_id ?? ''}
        onChange={(e) => onChange(results.find((p) => p.patient_id === e.target.value) ?? null)}
      >
        <option value="">Select who the appointment is for</option>
        {results.map((p) => (
          <option key={p.patient_id} value={p.patient_id}>
            {p.full_name} ({p.relationship})
          </option>
        ))}
      </select>
    )
  }

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
        <span>
          <span className="font-medium text-slate-800">{value.full_name}</span>
          <span className="ml-2 font-mono text-slate-500">{value.patient_id}</span>
          <span className="ml-2 text-slate-500">{value.phone}</span>
        </span>
        <button type="button" className="text-brand-600 hover:underline" onClick={() => onChange(null)}>
          Change
        </button>
      </div>
    )
  }

  const search = async () => {
    const found = await listPatients({ q, limit: 10 })
    // A scanned QR / exact ID selects immediately
    const exact = found.find((p) => p.patient_id === q.trim().toUpperCase())
    if (exact) return onChange(exact)
    setResults(found)
    setSearched(true)
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          className={inputClass}
          placeholder="Scan QR or search by Patient ID, name or phone"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              search()
            }
          }}
        />
        <button type="button" className={secondaryButton} onClick={search}>
          Search
        </button>
      </div>
      {results.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
          {results.map((p) => (
            <li key={p.patient_id}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                onClick={() => onChange(p)}
              >
                <span className="font-medium">{p.full_name}</span>
                <span className="ml-2 font-mono text-slate-500">{p.patient_id}</span>
                <span className="ml-2 text-slate-500">{p.phone}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {searched && results.length === 0 && <p className="text-sm text-slate-500">No patients found.</p>}
    </div>
  )
}
