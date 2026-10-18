import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { fetchPatientLinkPdf, getPatientLinkVersion } from '../../api/prescriptions'
import Logo from '../../components/Logo'
import { LANGS } from '../../components/prescriptions/options'
import { errorMessage, formatDate, inputClass, primaryButton, secondaryButton } from '../../components/ui'

/** Opened from the WhatsApp / SMS / email link (no login; the token in the link expires). */
export default function PatientPrescriptionPage() {
  const { publicId } = useParams()
  const [params, setParams] = useSearchParams()
  const token = params.get('token') ?? ''
  const lang = LANGS.some(([v]) => v === params.get('lang')) ? params.get('lang') : 'en'
  const [rx, setRx] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getPatientLinkVersion(publicId, token)
      .then(setRx)
      .catch((err) => setError(errorMessage(err, 'This prescription link is not valid')))
  }, [publicId, token])

  const pdf = async (download) => {
    setBusy(true)
    try {
      const url = URL.createObjectURL(await fetchPatientLinkPdf(publicId, token, lang))
      if (download) {
        const a = Object.assign(document.createElement('a'), { href: url, download: `${publicId}-${lang}.pdf` })
        a.click()
      } else {
        window.open(url, '_blank', 'noopener')
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (err) {
      setError(errorMessage(err, 'Could not load the PDF'))
    } finally {
      setBusy(false)
    }
  }

  const c = rx?.content
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="mx-auto max-w-lg space-y-5">
        <Logo />
        {error && <p className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
        {!rx && !error && <p className="text-slate-500">Loading...</p>}
        {rx && (
          <>
            <div>
              <h1 className="text-xl font-semibold text-slate-800">Your prescription</h1>
              <p className="text-sm text-slate-500">
                {rx.letterhead.clinic_name} | {rx.letterhead.doctor_name} | {formatDate(rx.finalized_at)}
              </p>
              {rx.superseded && (
                <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">The doctor has since updated this prescription. Ask the clinic for the latest copy.</p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-4">
              <select className={`${inputClass} w-auto!`} value={lang} onChange={(e) => setParams({ token, lang: e.target.value }, { replace: true })} aria-label="Language">
                {LANGS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button className={primaryButton} disabled={busy} onClick={() => pdf(true)}>
                Download PDF
              </button>
              <button className={secondaryButton} disabled={busy} onClick={() => pdf(false)}>
                Open
              </button>
            </div>

            <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 text-sm">
              {c.medicines.length > 0 && (
                <section>
                  <h2 className="mb-1 font-semibold text-slate-800">Medicines</h2>
                  <ol className="list-decimal space-y-1 pl-5">
                    {c.medicines.map((m, i) => (
                      <li key={i}>
                        <b>{m.name}</b> {[m.dose, m.frequency, m.duration, m.instructions].filter(Boolean).join(' | ')}
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {c.investigations.length > 0 && (
                <section>
                  <h2 className="mb-1 font-semibold text-slate-800">Tests advised</h2>
                  <p>{c.investigations.map((i) => i.name).join(', ')}</p>
                </section>
              )}
              {[
                ['Advice', c.advice],
                ['Diet and lifestyle', c.diet_lifestyle],
              ].map(
                ([title, text]) =>
                  text?.trim() && (
                    <section key={title}>
                      <h2 className="mb-1 font-semibold text-slate-800">{title}</h2>
                      <p className="whitespace-pre-line">{text}</p>
                    </section>
                  ),
              )}
              {c.follow_up?.date && (
                <p>
                  <b>Follow-up:</b> {formatDate(c.follow_up.date)}
                  {c.follow_up.note && ` - ${c.follow_up.note}`}
                </p>
              )}
              <p className="text-xs text-slate-400">The PDF in your language is the complete prescription. Code {rx.public_id}.</p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
