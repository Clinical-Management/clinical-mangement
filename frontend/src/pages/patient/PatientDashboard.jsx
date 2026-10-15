import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listPatients } from '../../api/patients'
import { labelOf, RELATIONSHIPS } from '../../components/patients/options'
import PatientQRCard from '../../components/patients/PatientQRCard'
import { cardClass, errorMessage, primaryButton } from '../../components/ui'
import { PATIENT_BASE } from '../../routes/roles'

const base = PATIENT_BASE.patient

// A patient account manages its own profile plus family members (children, parents, ...)
export default function PatientDashboard() {
  const [profiles, setProfiles] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listPatients()
      .then(setProfiles)
      .catch((err) => setError(errorMessage(err, 'Could not load profiles')))
  }, [])

  if (error) return <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
  if (!profiles) return <p className="text-slate-500">Loading...</p>

  const hasSelf = profiles.some((p) => p.relationship === 'self')

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">My profiles</h1>
          <p className="text-sm text-slate-500">Show a QR code at reception for quick check-in.</p>
        </div>
        {hasSelf && (
          <Link to={`${base}/new`} className={primaryButton}>
            Add family member
          </Link>
        )}
      </div>

      {!hasSelf && (
        <div className="rounded-xl bg-brand-gradient p-5 text-white shadow-sm">
          <h2 className="font-semibold">Complete your patient profile</h2>
          <p className="mt-1 text-sm text-white/85">
            We need a few details before you can book visits. You can add family members afterwards.
          </p>
          <Link
            to={`${base}/new?relationship=self`}
            className="mt-3 inline-block rounded-md bg-white px-4 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50"
          >
            Complete profile
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {profiles.map((p) => (
          <Link
            key={p.patient_id}
            to={`${base}/${p.patient_id}`}
            className={`${cardClass} flex items-center gap-4 transition hover:border-accent-600`}
          >
            <PatientQRCard patientId={p.patient_id} size={88} downloadable={false} />
            <div>
              <p className="font-semibold text-slate-800">{p.full_name}</p>
              <p className="text-sm text-slate-500">
                {labelOf(RELATIONSHIPS, p.relationship)} | {p.age != null ? `${p.age} yrs` : 'Age unknown'}
              </p>
              {!p.voicebot_allowed && <p className="mt-1 text-xs text-amber-700">Voice assistant consent pending</p>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
