import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getPatient, updatePatient } from '../../api/patients'
import PatientForm from '../../components/patients/PatientForm'
import { errorMessage } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE, ROLES } from '../../routes/roles'

export default function EditPatientPage() {
  const { patientId } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getPatient(patientId)
      .then(setPatient)
      .catch((err) => setError(errorMessage(err, 'Could not load patient')))
  }, [patientId])

  const submit = async (payload) => {
    setError('')
    try {
      await updatePatient(patientId, payload)
      navigate(`${PATIENT_BASE[user.role]}/${patientId}`)
    } catch (err) {
      setError(errorMessage(err, 'Could not save changes'))
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const relationshipMode =
    patient?.relationship === 'self' ? 'locked' : user.role === ROLES.PATIENT ? 'required' : 'optional'

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Edit {patient?.full_name ?? 'patient'}</h1>
      {error && <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {patient && (
        <PatientForm patient={patient} showRelationship={relationshipMode} submitLabel="Save changes" onSubmit={submit} />
      )}
    </div>
  )
}
