import { useEffect, useState } from 'react'
import { createUser, getSecurity, listStaff, resetUserMfa, resetUserPassword, saveSecurity, updateUser } from '../../api/admin'
import { cardClass, errorMessage, formatDate, inputClass, labelClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'

const ROLES = [
  ['doctor', 'Doctor'],
  ['receptionist', 'Receptionist'],
  ['admin', 'Admin'],
]
const EMPTY = { full_name: '', email: '', password: '', role: 'receptionist' }

/** Staff accounts: add, change role, deactivate, reset two-step sign-in or password. */
export default function StaffPage() {
  const { user: me } = useAuth()
  const [staff, setStaff] = useState([])
  const [security, setSecurity] = useState(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = () => listStaff().then(setStaff)
  useEffect(() => {
    load()
    getSecurity().then(setSecurity)
  }, [])

  const act = async (fn, done) => {
    setError('')
    setMessage('')
    try {
      await fn()
      if (done) setMessage(done)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  const add = (e) => {
    e.preventDefault()
    act(async () => {
      await createUser(form)
      setForm(EMPTY)
      setAdding(false)
    }, 'Account created. Share the password privately; they will set up two-step sign-in at first sign-in.')
  }

  const resetPassword = (u) => {
    const password = window.prompt(`New temporary password for ${u.full_name} (at least 8 characters)`)
    if (password) act(() => resetUserPassword(u.id, password), `Password reset for ${u.full_name}.`)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-800">Staff</h1>
        <button className={adding ? secondaryButton : primaryButton} onClick={() => setAdding(!adding)}>
          {adding ? 'Close' : 'Add staff member'}
        </button>
      </div>
      {error && <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {message && <p className="rounded-md bg-accent-50 px-4 py-3 text-sm text-accent-700">{message}</p>}

      {adding && (
        <form onSubmit={add} className={`${cardClass} grid gap-4 sm:grid-cols-2`}>
          {[
            ['full_name', 'Full name', 'text'],
            ['email', 'Email', 'email'],
            ['password', 'Temporary password', 'text'],
          ].map(([key, label, type]) => (
            <label key={key}>
              <span className={labelClass}>{label}</span>
              <input className={inputClass} type={type} required minLength={key === 'password' ? 8 : 1} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
            </label>
          ))}
          <label>
            <span className={labelClass}>Role</span>
            <select className={inputClass} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end sm:col-span-2">
            <button className={primaryButton}>Create account</button>
          </div>
        </form>
      )}

      {security && (
        <label className={`${cardClass} flex items-start gap-3`}>
          <input
            type="checkbox"
            className="mt-1"
            checked={security.staff_mfa_required}
            onChange={(e) => act(async () => setSecurity(await saveSecurity({ staff_mfa_required: e.target.checked })))}
          />
          <span>
            <span className="block text-sm font-medium text-slate-800">Require two-step sign-in for all staff</span>
            <span className="text-sm text-slate-500">Staff without it set up are asked to set it up at their next sign-in.</span>
          </span>
        </label>
      )}

      <div className={`${cardClass} overflow-x-auto p-0!`}>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Role</th>
              <th className="px-4 py-2 font-medium">Two-step</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Added</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {staff.map((u) => (
              <tr key={u.id} className={u.is_active ? '' : 'text-slate-400'}>
                <td className="px-4 py-2">
                  <span className="font-medium">{u.full_name}</span>
                  <span className="block text-xs text-slate-500">{u.email}</span>
                </td>
                <td className="px-4 py-2">
                  <select
                    className={`${inputClass} w-auto! py-1`}
                    value={u.role}
                    disabled={u.id === me.id}
                    onChange={(e) => act(() => updateUser(u.id, { role: e.target.value }), `${u.full_name} is now ${e.target.value}.`)}
                    aria-label={`Role of ${u.full_name}`}
                  >
                    {ROLES.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2">{u.mfa_enabled ? 'On' : 'Off'}</td>
                <td className="px-4 py-2">{u.is_active ? 'Active' : 'Deactivated'}</td>
                <td className="px-4 py-2">{formatDate(u.created_at)}</td>
                <td className="space-x-3 px-4 py-2 text-right whitespace-nowrap">
                  {u.mfa_enabled && (
                    <button className="text-brand-600 hover:underline" onClick={() => act(() => resetUserMfa(u.id), `${u.full_name} will set up two-step sign-in again.`)}>
                      Reset two-step
                    </button>
                  )}
                  <button className="text-brand-600 hover:underline" onClick={() => resetPassword(u)}>
                    Reset password
                  </button>
                  {u.id !== me.id && (
                    <button className={u.is_active ? 'text-red-600 hover:underline' : 'text-brand-600 hover:underline'} onClick={() => act(() => updateUser(u.id, { is_active: !u.is_active }))}>
                      {u.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
