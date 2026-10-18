import { useEffect, useState } from 'react'
import { deliverVersion, listDeliveries, listVersions } from '../../api/prescriptions'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, primaryButton, secondaryButton } from '../ui'
import { LANGS, openPdf } from './options'

const CHANNELS = [
  ['print', 'Print'],
  ['whatsapp', 'WhatsApp'],
  ['sms', 'SMS link'],
  ['email', 'Email'],
  ['patient_app', 'Patient app'],
]
const STATUS_TEXT = { sent: 'Sent', link_ready: 'Link ready', published: 'In patient app', recorded: 'Printed', failed: 'Failed' }

/** Finalized versions: view the clinic or patient copy, and deliver it. */
export default function PrescriptionVersions({ appt, refreshKey, canDeliver = true }) {
  const [versions, setVersions] = useState([])
  const [log, setLog] = useState([])
  const [selected, setSelected] = useState(null)
  const [lang, setLang] = useState('en')
  const [to, setTo] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listVersions(appt.id).then((vs) => {
      setVersions(vs)
      setSelected((s) => (vs.find((v) => v.id === s) ? s : (vs[0]?.id ?? null)))
    })
    if (canDeliver) listDeliveries(appt.id).then(setLog).catch(() => {})
  }, [appt.id, canDeliver, refreshKey])

  if (!versions.length) return null
  const version = versions.find((v) => v.id === selected)

  const send = async (channel) => {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      if (channel === 'print') await openPdf(version.id, { lang, copy: lang === 'en' ? 'clinic' : 'patient' })
      const r = await deliverVersion(version.id, { channel, language: lang, to: to.trim() || null })
      setResult(r)
      if (r.share_url) window.open(r.share_url, '_blank', 'noopener')
      setLog(await listDeliveries(appt.id))
    } catch (err) {
      setError(errorMessage(err, 'Could not deliver'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={`${cardClass} space-y-4`}>
      <h2 className="text-sm font-semibold text-slate-800">Finalized prescriptions</h2>
      <div className="flex flex-wrap gap-2">
        {versions.map((v) => (
          <button
            key={v.id}
            onClick={() => setSelected(v.id)}
            className={`rounded-md border px-3 py-1.5 text-sm ${selected === v.id ? 'border-accent-600 bg-accent-50 text-accent-700' : 'border-slate-200 text-slate-600'}`}
          >
            v{v.version} {v.superseded ? '(superseded)' : '(current)'}
            <span className="ml-1 text-xs text-slate-400">{formatDate(v.finalized_at)}</span>
          </button>
        ))}
      </div>

      {version && (
        <>
          <p className="text-xs text-slate-500">
            {version.public_id} | finalized {formatDate(version.finalized_at)} {formatTime(version.finalized_at)} by {version.finalized_by_role}
            {version.override_reason && ` | warnings overridden: ${version.override_reason}`}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button className={secondaryButton} onClick={() => openPdf(version.id, { copy: 'clinic' })}>
              Clinic copy (PDF)
            </button>
            <select className={`${inputClass} w-auto!`} value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Patient copy language">
              {LANGS.map(([value, label]) => (
                <option key={value} value={value}>
                  Patient copy: {label}
                </option>
              ))}
            </select>
            <button className={secondaryButton} onClick={() => openPdf(version.id, { copy: 'patient', lang })}>
              Patient copy (PDF)
            </button>
          </div>

          {canDeliver && (
            <div className="space-y-2 rounded-lg bg-slate-50 p-3">
              <p className="text-xs font-medium text-slate-600">Deliver the {LANGS.find(([v]) => v === lang)[1]} patient copy</p>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  className={`${inputClass} w-56!`}
                  placeholder="Phone / email (default: patient's)"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
                {CHANNELS.map(([channel, label]) => (
                  <button key={channel} className={channel === 'print' ? primaryButton : secondaryButton} disabled={busy} onClick={() => send(channel)}>
                    {label}
                  </button>
                ))}
              </div>
              {result && (
                <p className={`text-sm ${result.status === 'failed' ? 'text-red-600' : 'text-accent-700'}`}>
                  {STATUS_TEXT[result.status]}: {result.detail}
                  {result.link && (
                    <button className="ml-2 underline" onClick={() => navigator.clipboard?.writeText(result.link)}>
                      Copy patient link
                    </button>
                  )}
                </p>
              )}
              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>
          )}
        </>
      )}

      {log.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-slate-500">Delivery log ({log.length})</summary>
          <ul className="mt-2 space-y-1 text-xs text-slate-600">
            {log.map((d) => (
              <li key={d.id}>
                {formatDate(d.at)} {formatTime(d.at)} - {CHANNELS.find(([c]) => c === d.channel)?.[1]} ({d.language}){d.to && ` to ${d.to}`}:{' '}
                {STATUS_TEXT[d.status]} by {d.by_role}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
