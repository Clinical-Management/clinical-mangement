import { formatTime } from '../ui'

/** Small autosave status line: "Saving...", "Saved 10:42", or the error with a retry. */
export default function SaveIndicator({ autosave }) {
  const { status, savedAt, error, flush } = autosave
  if (status === 'error') {
    return (
      <span className="text-xs text-red-600">
        Not saved: {error}{' '}
        <button className="underline" onClick={flush}>
          Retry
        </button>
      </span>
    )
  }
  const text = {
    pending: 'Unsaved changes...',
    saving: 'Saving...',
    saved: savedAt && `Saved ${formatTime(savedAt)}`,
  }[status]
  return <span className="text-xs text-slate-400">{text ?? ''}</span>
}
