import { useCallback, useEffect, useState } from 'react'
import { getQueue, listAppointments } from '../../api/appointments'
import { todayISO } from '../ui'

const POLL_MS = 15000

/** Today's queue (checked-in) plus booked-but-not-arrived appointments, refreshed while visible.
 *  Doctors automatically get only their own (the API scopes it). */
export default function useToday() {
  const [data, setData] = useState({ queue: [], expected: [], loaded: false })

  const load = useCallback(async () => {
    try {
      const today = todayISO()
      const [queue, expected] = await Promise.all([
        getQueue({ date: today }),
        listAppointments({ date: today, status: 'scheduled' }),
      ])
      setData({ queue, expected, loaded: true })
    } catch {
      // keep the last good data; the next poll retries
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

  const counts = {
    expected: data.expected.length,
    waiting: data.queue.filter((a) => a.status === 'waiting' || a.status === 'with_voicebot').length,
    in_consultation: data.queue.filter((a) => a.status === 'in_consultation').length,
    completed: data.queue.filter((a) => a.status === 'completed').length,
  }
  return { ...data, counts, reload: load }
}
