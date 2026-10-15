import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { acknowledgeAlert, listAlerts } from '../../api/history'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE } from '../../routes/roles'
import { formatTime } from '../ui'

const POLL_MS = 10000

function beep() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    osc.frequency.value = 880
    osc.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.4)
  } catch {
    // audio unavailable (e.g. before any user interaction) - the banner still shows
  }
}

/** Red-flag alerts raised by the voicebot, shown to front desk and doctors on every page. */
export default function AlertsBanner() {
  const { user } = useAuth()
  const [alerts, setAlerts] = useState([])
  const seen = useRef(new Set())

  const load = useCallback(async () => {
    try {
      const open = await listAlerts()
      if (open.some((a) => !seen.current.has(a.id))) beep()
      open.forEach((a) => seen.current.add(a.id))
      setAlerts(open)
    } catch {
      // transient errors: try again on the next poll
    }
  }, [])

  useEffect(() => {
    const tick = () => document.visibilityState === 'visible' && load()
    tick()
    const timer = setInterval(tick, POLL_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [load])

  if (!alerts.length) return null

  return (
    <div className="space-y-px">
      {alerts.map((a) => (
        <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 bg-red-600 px-6 py-2.5 text-sm text-white">
          <span>
            <b>URGENT</b> {formatTime(a.created_at)}: {a.message} (with {a.doctor_name})
          </span>
          <span className="flex gap-3">
            <Link to={`${APPOINTMENT_BASE[user.role]}/${a.appointment_id}`} className="underline">
              Open
            </Link>
            <button
              className="rounded bg-white/20 px-2 py-0.5 hover:bg-white/30"
              onClick={() => acknowledgeAlert(a.id).then(load)}
            >
              Acknowledge
            </button>
          </span>
        </div>
      ))}
    </div>
  )
}
