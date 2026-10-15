import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listPatients } from '../../api/patients'
import { GENDERS, labelOf } from '../../components/patients/options'
import { cardClass, errorMessage, inputClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { FRONT_DESK, PATIENT_BASE, ROLES } from '../../routes/roles'

// Staff patient search. Scanning a patient QR into the search box (scanners type
// the ID and press Enter) jumps straight to that patient for quick check-in.
export default function PatientListPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const base = PATIENT_BASE[user.role]
  const isFrontDesk = FRONT_DESK.includes(user.role)
  const showAllergies = user.role !== ROLES.RECEPTIONIST // no clinical access

  const [q, setQ] = useState('')
  const [flagged, setFlagged] = useState(false)
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const search = useCallback(
    async (query, onlyFlagged) => {
      setLoading(true)
      setError('')
      try {
        const results = await listPatients({ q: query || undefined, flagged: onlyFlagged || undefined })
        const exact = results.find((p) => p.patient_id === query.trim().toUpperCase())
        if (exact) return navigate(`${base}/${exact.patient_id}`)
        setPatients(results)
      } catch (err) {
        setError(errorMessage(err, 'Search failed'))
      } finally {
        setLoading(false)
      }
    },
    [base, navigate],
  )

  useEffect(() => {
    listPatients()
      .then(setPatients)
      .catch((err) => setError(errorMessage(err, 'Could not load patients')))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-800">Patients</h1>
        {isFrontDesk && (
          <Link to={`${base}/new`} className={primaryButton}>
            Register patient
          </Link>
        )}
      </div>

      <form
        className="flex flex-wrap items-center gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          search(q, flagged)
        }}
      >
        <input
          autoFocus
          className={`${inputClass} max-w-md`}
          placeholder="Scan QR or search by Patient ID, name or phone"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button className={secondaryButton}>Search</button>
        {isFrontDesk && (
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={flagged}
              onChange={(e) => {
                setFlagged(e.target.checked)
                search(q, e.target.checked)
              }}
            />
            Possible duplicates only
          </label>
        )}
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className={`${cardClass} overflow-x-auto p-0!`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Patient ID</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Age / Gender</th>
              <th className="px-4 py-3">Phone</th>
              {showAllergies && <th className="px-4 py-3">Allergies</th>}
            </tr>
          </thead>
          <tbody>
            {patients.map((p) => (
              <tr
                key={p.patient_id}
                onClick={() => navigate(`${base}/${p.patient_id}`)}
                className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
              >
                <td className="px-4 py-3 font-mono text-brand-700">
                  {p.patient_id}
                  {p.possible_duplicates.length > 0 && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 font-sans text-xs text-amber-800">dup?</span>
                  )}
                </td>
                <td className="px-4 py-3 font-medium text-slate-800">{p.full_name}</td>
                <td className="px-4 py-3 text-slate-600">
                  {p.age ?? '-'} / {labelOf(GENDERS, p.gender)}
                </td>
                <td className="px-4 py-3 text-slate-600">{p.phone}</td>
                {showAllergies && (
                  <td className="px-4 py-3 text-red-700">{p.medical?.allergies.map((a) => a.substance).join(', ')}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && patients.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No patients found</p>}
        {loading && <p className="p-6 text-center text-sm text-slate-500">Loading...</p>}
      </div>
    </div>
  )
}
