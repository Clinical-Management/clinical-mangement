import { useState } from 'react'
import { updateConsent } from '../../api/patients'
import { cardClass, errorMessage, formatDate, primaryButton } from '../ui'
import { CONSENT_ITEMS } from './options'

export default function ConsentPanel({ patient, onUpdated }) {
  const current = patient.consent
  const [draft, setDraft] = useState({
    data_storage: current.data_storage,
    voice_recording: current.voice_recording,
    ai_processing: current.ai_processing,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const dirty = CONSENT_ITEMS.some((i) => draft[i.key] !== current[i.key])

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      onUpdated(await updateConsent(patient.patient_id, draft))
    } catch (err) {
      setError(errorMessage(err, 'Could not update consent'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={cardClass}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">Consent</h2>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
            patient.voicebot_allowed ? 'bg-accent-50 text-accent-700' : 'bg-amber-50 text-amber-700'
          }`}
        >
          Voice assistant {patient.voicebot_allowed ? 'allowed' : 'not allowed'}
        </span>
      </div>

      <div className="space-y-3">
        {CONSENT_ITEMS.map((item) => (
          <label key={item.key} className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={draft[item.key]}
              // Withdrawing storage consent means deleting the record, which is handled by the clinic
              disabled={item.required}
              onChange={(e) => setDraft({ ...draft, [item.key]: e.target.checked })}
            />
            <span>
              <span className="font-medium text-slate-800">{item.label}</span>
              <span className="block text-slate-500">
                {item.description}
                {item.required && ' To withdraw this, please contact the clinic.'}
              </span>
            </span>
          </label>
        ))}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-slate-400">
          Last updated {formatDate(current.updated_at)} by {current.updated_by_role}
        </span>
        {dirty && (
          <button className={primaryButton} onClick={save} disabled={saving}>
            {saving ? 'Saving...' : 'Save consent'}
          </button>
        )}
      </div>
    </section>
  )
}
