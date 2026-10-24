import { useEffect, useState } from 'react'
import { getClinicSettings, saveClinicSettings } from '../../api/prescriptions'
import { cardClass, errorBox, errorMessage, inputClass, labelClass, primaryButton } from '../../components/ui'

const FIELDS = [
  ['name', 'Clinic name', 'Sunrise Family Clinic', true],
  ['address', 'Address', 'Shop 4, MG Road, Pune 411001'],
  ['phone', 'Phone', '+91 20 1234 5678'],
  ['email', 'Email', 'care@clinic.example'],
  ['registration', 'Establishment registration', 'e.g. Clinical Establishments Act reg. no.'],
  ['gstin', 'GSTIN (if registered)', '27ABCDE1234F1Z5'],
  ['upi_id', 'UPI ID for patient payments', 'clinic@okhdfc'],
]

/** Letterhead printed on prescriptions and receipts, plus GSTIN and the UPI ID patients pay to. */
export default function ClinicSettingsPage() {
  const [form, setForm] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getClinicSettings()
      .then((s) => setForm(Object.fromEntries(FIELDS.map(([k]) => [k, s[k] ?? '']))))
      .catch((err) => setError(errorMessage(err, 'Could not load the clinic settings')))
  }, [])

  const save = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')
    try {
      await saveClinicSettings(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])))
      setMessage('Saved. Prescriptions finalized from now on use this letterhead; earlier ones keep theirs.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  if (!form) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Loading...</p>

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Clinic details</h1>
      {error && <p className={errorBox}>{error}</p>}
      {message && <p className="rounded-md bg-accent-50 px-4 py-3 text-sm text-accent-700">{message}</p>}
      <form onSubmit={save} className={`${cardClass} space-y-4`}>
        <div className="grid gap-4 sm:grid-cols-2">
          {FIELDS.map(([key, label, placeholder, required]) => (
            <label key={key} className={key === 'address' ? 'sm:col-span-2' : ''}>
              <span className={labelClass}>
                {label}
                {required && ' *'}
              </span>
              <input className={inputClass} required={required} placeholder={placeholder} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
            </label>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          Each doctor's registration number, qualifications and signature are set on their page under Doctors.
        </p>
        <div className="flex justify-end">
          <button className={primaryButton}>Save letterhead</button>
        </div>
      </form>
    </div>
  )
}
