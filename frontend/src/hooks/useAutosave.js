import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Save `value` automatically shortly after it stops changing.
 * Returns { status: 'idle' | 'pending' | 'saving' | 'saved' | 'error', savedAt, error, flush }.
 * Pending changes are also saved when the component unmounts (e.g. leaving the page).
 */
export default function useAutosave(value, save, { delay = 1200, enabled = true } = {}) {
  const [status, setStatus] = useState('idle')
  const [savedAt, setSavedAt] = useState(null)
  const [error, setError] = useState('')
  const latest = useRef(value)
  const saved = useRef(JSON.stringify(value))
  const timer = useRef(null)
  const saveRef = useRef(save)

  useEffect(() => {
    saveRef.current = save
  }, [save])

  const flush = useCallback(async () => {
    clearTimeout(timer.current)
    const snapshot = JSON.stringify(latest.current)
    if (snapshot === saved.current) return
    setStatus('saving')
    try {
      await saveRef.current(latest.current)
      saved.current = snapshot
      setSavedAt(new Date())
      setError('')
      // more edits may have arrived while saving
      setStatus(JSON.stringify(latest.current) === snapshot ? 'saved' : 'pending')
    } catch (err) {
      setError(err.response?.data?.detail?.toString?.() || 'Could not save')
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    latest.current = value
    if (!enabled || JSON.stringify(value) === saved.current) return
    setStatus('pending')
    clearTimeout(timer.current)
    timer.current = setTimeout(flush, delay)
  }, [value, enabled, delay, flush])

  // Save anything outstanding when leaving
  useEffect(() => () => void flush(), [flush])

  /** Call after loading fresh data from the server so it isn't saved straight back. */
  const reset = useCallback((fresh) => {
    latest.current = fresh
    saved.current = JSON.stringify(fresh)
    setStatus('idle')
  }, [])

  return { status, savedAt, error, flush, reset }
}
