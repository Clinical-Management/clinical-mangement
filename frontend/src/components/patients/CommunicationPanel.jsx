import { useState } from 'react'
import { setCommunication } from '../../api/reminders'
import { cardClass, errorMessage, inputClass, labelClass } from '../ui'

const CHANNELS = [
  ['whatsapp', 'WhatsApp'],
  ['sms', 'SMS'],
  ['email', 'Email'],
  ['app', 'Patient app'],
]
const LANGS = [
  ['en', 'English'],
  ['hi', 'हिन्दी (Hindi)'],
  ['mr', 'मराठी (Marathi)'],
]

/** Language and channels for reminders, receipts and other messages. Saves on each change. */
export default function CommunicationPanel({ patient, editable }) {
  const [prefs, setPrefs] = useState(patient.communication ?? { language: 'en', channels: ['whatsapp', 'app'], reminders: true })
  const [status, setStatus] = useState('')

  const save = async (next) => {
    setPrefs(next)
    setStatus('Saving...')
    try {
      await setCommunication(patient.patient_id, next)
      setStatus('Saved')
    } catch (err) {
      setStatus(errorMessage(err, 'Could not save'))
    }
  }
  const toggle = (c) => save({ ...prefs, channels: prefs.channels.includes(c) ? prefs.channels.filter((x) => x !== c) : [...prefs.channels, c] })

  return (
    <section className={cardClass}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">Messages</h2>
        <span className="text-xs text-slate-500">{status}</span>
      </div>
      <div className="space-y-3 text-sm">
        <label className="block">
          <span className={labelClass}>Language</span>
          <select className={inputClass} disabled={!editable} value={prefs.language} onChange={(e) => save({ ...prefs, language: e.target.value })}>
            {LANGS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <div>
          <span className={labelClass}>Send on</span>
          <div className="flex flex-wrap gap-3">
            {CHANNELS.map(([v, l]) => (
              <label key={v} className="flex items-center gap-1.5">
                <input type="checkbox" disabled={!editable} checked={prefs.channels.includes(v)} onChange={() => toggle(v)} />
                {l}
              </label>
            ))}
          </div>
          {prefs.channels.includes('email') && !patient.email && <p className="mt-1 text-xs text-amber-700">No email address on file.</p>}
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" disabled={!editable} checked={prefs.reminders} onChange={(e) => save({ ...prefs, reminders: e.target.checked })} />
          Appointment reminders and follow-up messages
        </label>
      </div>
    </section>
  )
}
