import { useState } from 'react'
import { medicineRemindersOff, medicineRemindersOn, testReminder } from '../../api/reminders'
import { errorMessage, inputClass, secondaryButton, todayISO } from '../ui'

/** Patient app: opt in to medicine-time reminders and a repeat-test reminder for this prescription. */
export default function PatientReminders({ version }) {
  const [on, setOn] = useState(Boolean(version.medicine_reminders?.on))
  const tests = version.content.investigations.map((i) => i.name)
  const [testDate, setTestDate] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const toggle = async () => {
    setError('')
    setMessage('')
    try {
      if (on) {
        await medicineRemindersOff(version.id)
        setOn(false)
        setMessage('Medicine reminders turned off.')
      } else {
        const r = await medicineRemindersOn(version.id)
        setOn(true)
        setMessage(`${r.scheduled} reminders scheduled at your dose times.`)
      }
    } catch (err) {
      setError(errorMessage(err, 'Could not change reminders'))
    }
  }

  const remindTests = async () => {
    setError('')
    try {
      await testReminder(version.id, { date: testDate, tests })
      setMessage(`We'll remind you on ${testDate}.`)
      setTestDate('')
    } catch (err) {
      setError(errorMessage(err, 'Could not set the reminder'))
    }
  }

  return (
    <div className="space-y-2 rounded-lg bg-slate-50 p-3 text-sm">
      {version.content.medicines.length > 0 && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={on} onChange={toggle} />
          Remind me when it&apos;s time to take these medicines
        </label>
      )}
      {tests.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-slate-600">Remind me to repeat {tests.join(', ')} on</span>
          <input type="date" className={`${inputClass} w-auto! py-1`} min={todayISO()} value={testDate} onChange={(e) => setTestDate(e.target.value)} aria-label="Test date" />
          <button className={`${secondaryButton} py-1!`} disabled={!testDate} onClick={remindTests}>
            Set reminder
          </button>
        </div>
      )}
      {message && <p className="text-accent-700">{message}</p>}
      {error && <p className="text-red-600">{error}</p>}
    </div>
  )
}
