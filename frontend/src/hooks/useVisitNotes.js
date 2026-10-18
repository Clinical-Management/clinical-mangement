import { useEffect, useState } from 'react'
import { getNotes } from '../api/clinical'

/** Visit notes (examination, doctor notes, outcome, diagnoses), loaded once and shared by the editors. */
export default function useVisitNotes(appointmentId) {
  const [notes, setNotes] = useState(null)
  useEffect(() => {
    getNotes(appointmentId).then(setNotes)
  }, [appointmentId])
  return [notes, setNotes]
}
