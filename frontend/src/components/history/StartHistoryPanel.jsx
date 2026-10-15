import { QRCodeCanvas } from 'qrcode.react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { startHistory } from '../../api/history'
import { useAuth } from '../../context/AuthContext'
import { speechInputSupported } from '../../hooks/useSpeech'
import { HISTORY_BASE, ROLES } from '../../routes/roles'
import { cardClass, errorMessage, primaryButton, secondaryButton } from '../ui'

const HISTORY_STATUS = {
  in_progress: 'In progress',
  review: 'Patient reviewing summary',
  submitted: 'Submitted',
  escalated: 'Stopped: red flag',
}

/** Start the pre-visit voicebot for an appointment: on a clinic tablet/kiosk, on the patient's
 *  phone (QR), as typed chat, or as manual entry by a doctor/admin. */
export default function StartHistoryPanel({ appt }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [qr, setQr] = useState(null)
  const [error, setError] = useState('')

  const isPatient = user.role === ROLES.PATIENT
  const canEnterManually = [ROLES.ADMIN, ROLES.DOCTOR].includes(user.role)
  const open = ['scheduled', 'waiting', 'with_voicebot'].includes(appt.status)
  const historyBase = HISTORY_BASE[user.role]

  const start = async (mode, channel) => {
    setError('')
    try {
      const { session, link } = await startHistory({ appointment_id: appt.id, mode, channel })
      if (channel === 'staff') return navigate(`${historyBase}/${session.id}`)
      if (isPatient) return navigate(`/voice/${session.id}`)
      if (channel === 'patient_device') return setQr(`${window.location.origin}${link.path}`)
      window.open(link.path, '_blank', 'noopener')
    } catch (err) {
      setError(errorMessage(err, 'Could not start the history'))
    }
  }

  return (
    <section className={cardClass}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-800">Pre-visit history (voice assistant)</h2>
        {appt.history_status && (
          <span className="text-sm text-slate-500">
            {HISTORY_STATUS[appt.history_status] ?? appt.history_status}
            {historyBase && appt.history_session_id && (
              <Link to={`${historyBase}/${appt.history_session_id}`} className="ml-2 text-brand-600 hover:underline">
                View
              </Link>
            )}
          </span>
        )}
      </div>

      {open && appt.history_status !== 'submitted' && appt.history_status !== 'escalated' && (
        <div className="flex flex-wrap gap-2">
          {isPatient ? (
            <button className={primaryButton} onClick={() => start(speechInputSupported ? 'voice' : 'text', 'patient_device')}>
              {appt.history_status ? 'Continue' : 'Start'} on this phone
            </button>
          ) : (
            <>
              <button className={primaryButton} onClick={() => start('voice', 'clinic_device')}>
                Open on this tablet / kiosk
              </button>
              <button className={secondaryButton} onClick={() => start('voice', 'patient_device')}>
                Patient's phone (QR)
              </button>
              <button className={secondaryButton} onClick={() => start('text', 'clinic_device')}>
                Typed chat
              </button>
            </>
          )}
          {canEnterManually && (
            <button className={secondaryButton} onClick={() => start('manual', 'staff')}>
              Enter manually
            </button>
          )}
        </div>
      )}

      {qr && (
        <div className="mt-4 flex flex-wrap items-center gap-4 rounded-lg bg-slate-50 p-4">
          <QRCodeCanvas value={qr} size={160} marginSize={1} fgColor="#023b77" />
          <p className="max-w-xs text-sm text-slate-600">
            Ask the patient to scan this with their phone camera. The link works for a limited time and only for this
            visit.
          </p>
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </section>
  )
}
