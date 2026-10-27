import { useEffect, useState } from 'react'
import { markInboxRead, myInbox } from '../../api/reminders'
import { cardClass, formatDate, formatTime } from '../../components/ui'

const KINDS = { reminder: 'Appointment reminder', follow_up_booked: 'Follow-up booked', follow_up_nudge: 'Book your follow-up', medicine: 'Medicine time', repeat_test: 'Repeat test' }

// Links in messages are plain URLs: make them tappable
function Linked({ text }) {
  return text.split(/(https?:\/\/\S+)/g).map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a key={i} href={part} className="break-all text-brand-600 underline">
        {part.includes('do=confirm') ? 'Confirm' : 'Open'}
      </a>
    ) : (
      part
    ),
  )
}

/** Patient app: reminders and other messages from the clinic. */
export default function PatientInboxPage() {
  const [items, setItems] = useState(null)

  useEffect(() => {
    myInbox().then((list) => {
      setItems(list)
      if (list.some((n) => !n.read_at)) markInboxRead()
    })
  }, [])

  if (!items) return <p className="text-slate-500">Loading...</p>
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-2xl font-semibold text-slate-800">Messages</h1>
      {!items.length && <p className={`${cardClass} text-sm text-slate-500`}>No messages yet. Appointment reminders will appear here.</p>}
      {items.map((n) => (
        <div key={n.id} className={`${cardClass} py-4! ${n.read_at ? '' : 'border-l-4 border-l-accent-600'}`}>
          <p className="flex justify-between text-xs text-slate-500">
            <span className="font-medium text-brand-700">{KINDS[n.kind] ?? 'Message'}</span>
            <span>
              {formatDate(n.sent_at)} {formatTime(n.sent_at)}
            </span>
          </p>
          <p className="mt-1 text-sm text-slate-800">
            <Linked text={n.text} />
          </p>
        </div>
      ))}
    </div>
  )
}
