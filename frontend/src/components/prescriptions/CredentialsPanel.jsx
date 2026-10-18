import { useEffect, useState } from 'react'
import { fetchSignature, saveCredentials, uploadSignature } from '../../api/prescriptions'
import { cardClass, errorMessage, inputClass, labelClass, primaryButton } from '../ui'

const FIELDS = [
  ['registration_number', 'Registration number', 'e.g. MMC 2012/03/1234'],
  ['registration_council', 'Medical council', 'e.g. Maharashtra Medical Council'],
  ['qualifications', 'Qualifications', 'e.g. MBBS, MD (General Medicine)'],
]

/** Registration details and signature printed on the doctor's prescriptions. */
export default function CredentialsPanel({ doctor }) {
  const [form, setForm] = useState(() => Object.fromEntries(FIELDS.map(([k]) => [k, doctor[k] ?? ''])))
  const [signature, setSignature] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!doctor.has_signature) return
    let url
    fetchSignature(doctor.id)
      .then((blob) => setSignature((url = URL.createObjectURL(blob))))
      .catch(() => {})
    return () => url && URL.revokeObjectURL(url)
  }, [doctor.id, doctor.has_signature])

  const save = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')
    try {
      await saveCredentials(doctor.id, Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])))
      setMessage('Saved. New prescriptions will show these details.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  const upload = async (file) => {
    if (!file) return
    setError('')
    setMessage('')
    try {
      await uploadSignature(doctor.id, file)
      setSignature(URL.createObjectURL(file))
      setMessage('Signature uploaded.')
    } catch (err) {
      setError(errorMessage(err, 'Could not upload the signature'))
    }
  }

  return (
    <form onSubmit={save} className={`${cardClass} space-y-4`}>
      <div>
        <h2 className="text-sm font-semibold text-slate-800">Prescription letterhead</h2>
        <p className="text-xs text-slate-500">Printed under the doctor's name on every finalized prescription.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {FIELDS.map(([key, label, placeholder]) => (
          <label key={key}>
            <span className={labelClass}>{label}</span>
            <input className={inputClass} placeholder={placeholder} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <div className="grid h-16 w-48 place-items-center rounded-md border border-dashed border-slate-300 bg-slate-50">
          {signature ? <img src={signature} alt="Signature" className="max-h-14 max-w-44" /> : <span className="text-xs text-slate-400">No signature</span>}
        </div>
        <label className="text-sm text-brand-600 hover:underline">
          {signature ? 'Replace signature' : 'Upload signature'} (PNG/JPG, max 1 MB)
          <input type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => upload(e.target.files[0])} />
        </label>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {message && <p className="text-sm text-accent-700">{message}</p>}
      <div className="flex justify-end">
        <button className={primaryButton}>Save details</button>
      </div>
    </form>
  )
}
