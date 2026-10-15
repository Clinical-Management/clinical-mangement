import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../../api/auth'
import AuthCard from '../../components/AuthCard'
import { buttonClass, errorMessage, inputClass } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'

// Public sign-up creates patient accounts only; doctors are added by an admin.
export default function Register() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await register(form)
      await login(form.email, form.password)
      navigate('/patient')
    } catch (err) {
      setError(errorMessage(err, 'Registration failed'))
    } finally {
      setSubmitting(false)
    }
  }

  const field = (name, props) => (
    <input
      className={inputClass}
      required
      value={form[name]}
      onChange={(e) => setForm({ ...form, [name]: e.target.value })}
      {...props}
    />
  )

  return (
    <AuthCard title="Create patient account">
      <form onSubmit={handleSubmit} className="space-y-4">
        {field('full_name', { placeholder: 'Full name' })}
        {field('email', { type: 'email', placeholder: 'Email' })}
        {field('password', { type: 'password', placeholder: 'Password (min 8 chars)', minLength: 8 })}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className={buttonClass} disabled={submitting}>
          {submitting ? 'Creating...' : 'Create account'}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-500">
        Already registered?{' '}
        <Link to="/login" className="text-brand-600 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthCard>
  )
}
