import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { createPatient } from '../../api/patients'
import PatientForm from '../../components/patients/PatientForm'
import { errorMessage, formatDate, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE, ROLES } from '../../routes/roles'

function DuplicateWarning({ duplicate, base, onConfirm, onCancel }) {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h2 className="font-semibold text-amber-900">Possible duplicate patient</h2>
      <p className="mt-1 text-sm text-amber-800">{duplicate.message}</p>
      {duplicate.matches.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm">
          {duplicate.matches.map((m) => (
            <li key={m.patient_id}>
              <Link to={`${base}/${m.patient_id}`} className="font-mono text-brand-700 hover:underline">
                {m.patient_id}
              </Link>{' '}
              {m.full_name} | {m.date_of_birth ? formatDate(m.date_of_birth) : `age ${m.age}`} | {m.phone}
              <span className="ml-2 text-xs text-amber-700">matched on {m.matched_on.join(', ')}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-amber-800">
          If you have visited the clinic before, ask reception to link your existing record instead.
        </p>
      )}
      <div className="mt-4 flex gap-2">
        <button className={secondaryButton} onClick={onCancel}>
          Go back and edit
        </button>
        <button
          className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
          onClick={onConfirm}
        >
          This is a different person, register anyway
        </button>
      </div>
    </div>
  )
}

export default function RegisterPatientPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState('')
  const [duplicate, setDuplicate] = useState(null) // { message, matches, payload }

  const isOwner = user.role === ROLES.PATIENT
  const base = PATIENT_BASE[user.role]
  const isSelf = isOwner && params.get('relationship') === 'self'

  const submit = async (payload) => {
    setError('')
    try {
      const patient = await createPatient(payload)
      navigate(`${base}/${patient.patient_id}`)
    } catch (err) {
      const detail = err.response?.data?.detail
      if (err.response?.status === 409 && detail?.code === 'possible_duplicate') {
        setDuplicate({ ...detail, payload })
      } else {
        setError(errorMessage(err, 'Could not register patient'))
      }
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const title = isSelf ? 'Complete your profile' : isOwner ? 'Add a family member' : 'Register patient'

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">{title}</h1>

      {error && <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {duplicate && (
        <DuplicateWarning
          duplicate={duplicate}
          base={base}
          onCancel={() => setDuplicate(null)}
          onConfirm={() => {
            setDuplicate(null)
            submit({ ...duplicate.payload, allow_duplicate: true })
          }}
        />
      )}

      {/* Hidden (not unmounted) while the warning shows, so the entered data is kept */}
      <div className={duplicate ? 'hidden' : ''}>
        <PatientForm
          defaults={
            isSelf
              ? { full_name: user.full_name, email: user.email, relationship: 'self' }
              : { relationship: params.get('relationship') ?? '' }
          }
          showRelationship={isSelf ? 'locked' : isOwner ? 'required' : 'optional'}
          submitLabel="Register"
          onSubmit={submit}
        />
      </div>
    </div>
  )
}
