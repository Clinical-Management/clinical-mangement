import { useState } from 'react'
import { fetchMe, mfaDisable } from '../../api/auth'
import MfaSetup from '../../components/auth/MfaSetup'
import { cardClass, errorMessage, inputClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'

/** Staff: turn two-step sign-in on or off (e.g. when moving to a new phone). */
export default function SecurityPage() {
  const { user } = useAuth()
  const [enabled, setEnabled] = useState(user.mfa_enabled)
  const [mode, setMode] = useState(null) // 'setup' | 'disable'
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  const disable = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await mfaDisable(code)
      setEnabled(false)
      setMode(null)
      setCode('')
    } catch (err) {
      setError(errorMessage(err, 'That code didn’t work'))
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Security</h1>
      <section className={`${cardClass} space-y-4`}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Two-step sign-in</h2>
            <p className="text-sm text-slate-500">A code from your phone is needed as well as your password.</p>
          </div>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${enabled ? 'bg-accent-100 text-accent-700' : 'bg-slate-100 text-slate-600'}`}>
            {enabled ? 'On' : 'Off'}
          </span>
        </div>

        {mode === 'setup' && (
          <MfaSetup
            onDone={async () => {
              setEnabled(Boolean((await fetchMe()).mfa_enabled))
              setMode(null)
            }}
          />
        )}
        {mode === 'disable' && (
          <form onSubmit={disable} className="space-y-3">
            <p className="text-sm text-slate-600">Enter a current code (or a recovery code) to turn it off. If the clinic requires it, you&apos;ll set it up again at your next sign-in.</p>
            <input className={`${inputClass} font-mono tracking-widest`} required placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex gap-2">
              <button className={primaryButton}>Turn off</button>
              <button type="button" className={secondaryButton} onClick={() => setMode(null)}>
                Cancel
              </button>
            </div>
          </form>
        )}
        {!mode && (
          <button className={enabled ? secondaryButton : primaryButton} onClick={() => setMode(enabled ? 'disable' : 'setup')}>
            {enabled ? 'Turn off / move to a new phone' : 'Set up two-step sign-in'}
          </button>
        )}
      </section>
      <p className="text-xs text-slate-500">For safety you are signed out after 30 minutes without activity.</p>
    </div>
  )
}
