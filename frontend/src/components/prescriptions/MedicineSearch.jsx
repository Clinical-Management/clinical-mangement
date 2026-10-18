import { useRef, useState } from 'react'
import { searchMedicines } from '../../api/prescriptions'
import { inputClass } from '../ui'

/** Type a generic or brand name; picking a result fills the medicine with its usual dosing. */
export default function MedicineSearch({ value, onChange, onPick }) {
  const [results, setResults] = useState([])
  const timer = useRef(null)

  const search = (q) => {
    onChange(q)
    clearTimeout(timer.current)
    if (q.trim().length < 2) return setResults([])
    timer.current = setTimeout(() => searchMedicines(q).then(setResults).catch(() => setResults([])), 200)
  }

  const pick = (m) => {
    const d = m.defaults ?? {}
    onPick({
      name: m.matched_brand ?? m.generic,
      medicine_id: m.id,
      generic: m.generic,
      brand: m.matched_brand ?? '',
      dose: d.dose ?? '',
      frequency: d.frequency ?? '',
      duration: d.duration ?? '',
      route: d.route ?? m.routes?.[0] ?? '',
      instructions: d.instructions ?? '',
    })
    setResults([])
  }

  return (
    <div className="relative">
      <input
        className={`${inputClass} py-1.5`}
        placeholder="Generic or brand, e.g. Dolo"
        value={value}
        onChange={(e) => search(e.target.value)}
        onBlur={() => setTimeout(() => setResults([]), 150)}
      />
      {results.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-72 w-80 overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {results.map((m) => (
            <li key={m.id}>
              <button type="button" className="w-full px-3 py-2 text-left text-sm hover:bg-brand-50" onMouseDown={() => pick(m)}>
                <span className="font-medium text-slate-800">{m.matched_brand ?? m.generic}</span>
                {m.matched_brand && <span className="ml-1 text-slate-500">({m.generic})</span>}
                <span className="block text-xs text-slate-500">
                  {m.class_label}
                  {m.forms?.length > 0 && ` | ${m.forms.slice(0, 3).join(', ')}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
