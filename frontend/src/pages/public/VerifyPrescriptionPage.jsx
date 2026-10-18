import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { verifyPrescription } from '../../api/prescriptions'
import Logo from '../../components/Logo'
import { errorMessage, formatDate, formatTime } from '../../components/ui'

/** Opened by scanning the QR code on a prescription (no login): is it genuine and current? */
export default function VerifyPrescriptionPage() {
  const { publicId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    verifyPrescription(publicId)
      .then(setData)
      .catch((err) => setError(errorMessage(err, 'Could not check this prescription')))
  }, [publicId])

  const verdict = !data
    ? null
    : !data.valid
      ? { box: 'bg-red-50 text-red-800 border-red-300', title: 'Not genuine', text: 'The signature does not match. Do not dispense; contact the clinic.' }
      : !data.current
        ? { box: 'bg-amber-50 text-amber-900 border-amber-300', title: 'Genuine, but replaced', text: `The doctor issued a newer version (v${data.superseded_by_version}). Ask the patient for the latest copy.` }
        : { box: 'bg-accent-50 text-accent-800 border-accent-300', title: 'Genuine and current', text: 'Signed by the clinic and not changed since.' }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="mx-auto max-w-lg space-y-5">
        <Logo />
        <h1 className="text-xl font-semibold text-slate-800">Prescription verification</h1>
        {error && <p className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
        {!data && !error && <p className="text-slate-500">Checking...</p>}
        {data && (
          <>
            <div className={`rounded-xl border-2 px-4 py-3 ${verdict.box}`}>
              <p className="text-lg font-semibold">{verdict.title}</p>
              <p className="text-sm">{verdict.text}</p>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl border border-slate-200 bg-white p-4 text-sm">
              <dt className="text-slate-500">Code</dt>
              <dd className="font-mono">
                {data.public_id} (v{data.version})
              </dd>
              <dt className="text-slate-500">Clinic</dt>
              <dd>{data.clinic_name}</dd>
              <dt className="text-slate-500">Doctor</dt>
              <dd>
                {data.doctor_name}
                {data.registration_number && <span className="text-slate-500"> (Reg. {data.registration_number})</span>}
              </dd>
              <dt className="text-slate-500">Patient</dt>
              <dd>
                {data.patient_initials}, {data.patient_age ?? '-'} y, {data.patient_gender ?? '-'}
              </dd>
              <dt className="text-slate-500">Issued</dt>
              <dd>
                {formatDate(data.finalized_at)} {formatTime(data.finalized_at)}
              </dd>
            </dl>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-sm font-semibold text-slate-800">Medicines</h2>
              {data.medicines.length ? (
                <ol className="list-decimal space-y-1 pl-5 text-sm">
                  {data.medicines.map((m, i) => (
                    <li key={i}>
                      <b>{m.name}</b> {[m.dose, m.frequency, m.duration].filter(Boolean).join(' | ')}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-slate-500">No medicines on this prescription.</p>
              )}
            </div>
            <p className="text-xs text-slate-400">Compare these medicines with the paper or PDF copy before dispensing.</p>
          </>
        )}
      </div>
    </div>
  )
}
