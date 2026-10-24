import { useEffect, useState } from 'react'
import { mfaEnable, mfaSetup } from '../../api/auth'
import { buttonClass, errorMessage, inputClass } from '../ui'

/** Scan a QR code with an authenticator app, confirm a code, then save the recovery codes.
 *  `mfaToken` during sign-in; omitted when already signed in. */
export default function MfaSetup({ mfaToken, onDone }) {
  const [setup, setSetup] = useState(null)
  const [code, setCode] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    mfaSetup(mfaToken)
      .then(setSetup)
      .catch((err) => setError(errorMessage(err, 'Could not start the setup')))
  }, [mfaToken])

  const confirm = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      setResult(await mfaEnable(mfaToken, code))
    } catch (err) {
      setError(errorMessage(err, 'That code didn’t match'))
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-700">
          Two-step sign-in is on. Save these recovery codes somewhere safe. Each one signs you in once if you lose your phone. They won&apos;t be
          shown again.
        </p>
        <ul className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 font-mono text-sm text-slate-800">
          {result.recovery_codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <button type="button" className="text-sm text-brand-600 hover:underline" onClick={() => navigator.clipboard?.writeText(result.recovery_codes.join('\n'))}>
          Copy codes
        </button>
        <button type="button" className={buttonClass} onClick={() => onDone(result)}>
          I&apos;ve saved them, continue
        </button>
      </div>
    )
  }

  return (
    <form onSubmit={confirm} className="space-y-4">
      <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
        <li>Install an authenticator app (Google Authenticator, Microsoft Authenticator or Authy).</li>
        <li>Scan this code with the app.</li>
        <li>Enter the 6-digit code the app shows.</li>
      </ol>
      {setup ? (
        <div className="flex flex-col items-center gap-2">
          <img src={setup.qr_png} alt="QR code for the authenticator app" className="h-44 w-44" />
          <details className="text-center text-xs text-slate-500">
            <summary className="cursor-pointer">Can&apos;t scan? Enter the key instead</summary>
            <code className="mt-1 block break-all text-slate-700">{setup.secret}</code>
          </details>
        </div>
      ) : (
        !error && <p className="text-center text-sm text-slate-500">Preparing...</p>
      )}
      <input
        className={`${inputClass} text-center font-mono text-lg tracking-widest`}
        inputMode="numeric"
        autoComplete="one-time-code"
        placeholder="123456"
        required
        value={code}
        onChange={(e) => setCode(e.target.value)}
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className={buttonClass} disabled={busy || !setup}>
        {busy ? 'Checking...' : 'Turn on two-step sign-in'}
      </button>
    </form>
  )
}
