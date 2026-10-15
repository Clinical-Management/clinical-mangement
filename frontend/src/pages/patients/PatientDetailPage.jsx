import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getFamily, getPatient } from '../../api/patients'
import ConsentPanel from '../../components/patients/ConsentPanel'
import MedicalInfoPanel from '../../components/patients/MedicalInfoPanel'
import { BLOOD_GROUPS, GENDERS, labelOf, RELATIONSHIPS } from '../../components/patients/options'
import PatientQRCard from '../../components/patients/PatientQRCard'
import { cardClass, errorMessage, formatDate, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, FRONT_DESK, PATIENT_BASE, ROLES } from '../../routes/roles'

function Detail({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-800">{children || '-'}</dd>
    </div>
  )
}

const formatAddress = (a) =>
  a && [a.line1, a.line2, a.city, a.state, a.postal_code, a.country].filter(Boolean).join(', ')

export default function PatientDetailPage() {
  const { patientId } = useParams()
  const { user } = useAuth()
  const [patient, setPatient] = useState(null)
  const [family, setFamily] = useState([])
  const [error, setError] = useState('')

  const base = PATIENT_BASE[user.role]
  const canEditDetails = user.role !== ROLES.DOCTOR
  const allergies = patient?.medical?.allergies ?? []

  useEffect(() => {
    Promise.all([getPatient(patientId), getFamily(patientId)])
      .then(([p, f]) => {
        setPatient(p)
        setFamily(f)
      })
      .catch((err) => setError(errorMessage(err, 'Could not load patient')))
  }, [patientId])

  if (error) return <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
  if (!patient) return <p className="text-slate-500">Loading...</p>

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {FRONT_DESK.includes(user.role) && patient.possible_duplicates.length > 0 && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Registered despite a duplicate warning. Possible matches:{' '}
          {patient.possible_duplicates.map((id) => (
            <Link key={id} to={`${base}/${id}`} className="mr-2 font-mono text-brand-700 hover:underline">
              {id}
            </Link>
          ))}
        </p>
      )}

      <section className={`${cardClass} flex flex-col gap-6 sm:flex-row sm:items-start`}>
        <PatientQRCard patientId={patient.patient_id} />
        <div className="flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold text-slate-800">{patient.full_name}</h1>
              <p className="text-sm text-slate-500">
                {patient.age != null ? `${patient.age} yrs` : 'Age unknown'} | {labelOf(GENDERS, patient.gender)} |
                Blood group {labelOf(BLOOD_GROUPS, patient.blood_group)}
                {patient.relationship && ` | ${labelOf(RELATIONSHIPS, patient.relationship)}`}
              </p>
            </div>
            <div className="flex gap-2">
              {canEditDetails && (
                <Link to={`${base}/${patient.patient_id}/edit`} className={secondaryButton}>
                  Edit details
                </Link>
              )}
              {canEditDetails && (
                <Link
                  to={`${APPOINTMENT_BASE[user.role]}/new?patient_id=${patient.patient_id}`}
                  className={primaryButton}
                >
                  Book appointment
                </Link>
              )}
            </div>
          </div>

          {allergies.length > 0 && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
              <span className="font-semibold">Allergies:</span> {allergies.map((a) => a.substance).join(', ')}
            </p>
          )}

          <dl className="mt-4 grid gap-4 sm:grid-cols-3">
            <Detail label="Date of birth">{patient.date_of_birth ? formatDate(patient.date_of_birth) : 'Not known'}</Detail>
            <Detail label="Phone">{patient.phone}</Detail>
            <Detail label="Email">{patient.email}</Detail>
            <Detail label="Address">{formatAddress(patient.address)}</Detail>
            <Detail label="Emergency contact">
              {patient.emergency_contact &&
                `${patient.emergency_contact.name} (${patient.emergency_contact.relationship}), ${patient.emergency_contact.phone}`}
            </Detail>
            <Detail label="Registered">{formatDate(patient.created_at)}</Detail>
          </dl>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* medical is null for roles without clinical access (receptionists) */}
        {patient.medical && (
          <div className="lg:col-span-2">
            <MedicalInfoPanel patient={patient} onUpdated={setPatient} />
          </div>
        )}
        <div className="space-y-5">
          {/* key: reset the draft when consent is saved elsewhere */}
          <ConsentPanel key={patient.consent.updated_at} patient={patient} onUpdated={setPatient} />

          <section className={cardClass}>
            <h2 className="mb-3 text-sm font-semibold text-slate-800">Family</h2>
            {family.length === 0 ? (
              <p className="text-sm text-slate-400">No linked family profiles</p>
            ) : (
              <ul className="space-y-2">
                {family.map((f) => (
                  <li key={f.patient_id} className="text-sm">
                    <Link to={`${base}/${f.patient_id}`} className="font-medium text-brand-700 hover:underline">
                      {f.full_name}
                    </Link>
                    <span className="ml-2 text-slate-500">
                      {f.relationship ? labelOf(RELATIONSHIPS, f.relationship) : 'Same phone'} | {f.patient_id}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
