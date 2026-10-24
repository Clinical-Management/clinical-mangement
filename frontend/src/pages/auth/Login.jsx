import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { mfaVerify } from '../../api/auth'
import AuthCard from '../../components/AuthCard'
import MfaSetup from '../../components/auth/MfaSetup'
import { buttonClass, errorMessage, inputClass } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { ROLE_HOME } from '../../routes/roles'

export default function Login() {
  const { login, startSession, endedReason } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [step, setStep] = useState(null) // null | { kind: 'code' | 'setup', mfaToken }
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const enter = (user) => navigate(ROLE_HOME[user.role])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const res = await login(form.email, form.password)
      if (res.mfa_token) setStep({ kind: res.mfa_required ? 'code' : 'setup', mfaToken: res.mfa_token })
      else enter(res)
    } catch (err) {
      setError(errorMessage(err, 'Login failed'))
    } finally {
      setSubmitting(false)
    }
  }

  const verify = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      enter(startSession(await mfaVerify(step.mfaToken, code)))
    } catch (err) {
      setError(errorMessage(err, 'That code didn’t work'))
    } finally {
      setSubmitting(false)
    }
  }

  if (step?.kind === 'setup') {
    return (
      <AuthCard title="Set up two-step sign-in">
        <p className="mb-4 text-sm text-slate-600">The clinic requires a code from your phone, as well as your password, for staff accounts.</p>
        <MfaSetup mfaToken={step.mfaToken} onDone={(result) => enter(startSession(result.session))} />
      </AuthCard>
    )
  }

  if (step?.kind === 'code') {
    return (
      <AuthCard title="Enter your code">
        <form onSubmit={verify} className="space-y-4">
          <p className="text-sm text-slate-600">Open your authenticator app and enter the 6-digit code. Lost your phone? Enter a recovery code.</p>
          <input
            className={`${inputClass} text-center font-mono text-lg tracking-widest`}
            autoFocus
            autoComplete="one-time-code"
            placeholder="123456"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button className={buttonClass} disabled={submitting}>
            {submitting ? 'Checking...' : 'Sign in'}
          </button>
          <button type="button" className="w-full text-sm text-slate-500 hover:underline" onClick={() => setStep(null)}>
            Back
          </button>
        </form>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Sign in">
      {endedReason && <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{endedReason}</p>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          className={inputClass}
          type="email"
          placeholder="Email"
          required
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <input
          className={inputClass}
          type="password"
          placeholder="Password"
          required
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className={buttonClass} disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-500">
        New patient?{' '}
        <Link to="/register" className="text-brand-600 hover:underline">
          Create an account
        </Link>
      </p>
    </AuthCard>
  )
}
