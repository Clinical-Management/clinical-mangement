import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getBill, payBill, saveBill, waiveBill } from '../../api/workspace'
import { useAuth } from '../../context/AuthContext'
import useAutosave from '../../hooks/useAutosave'
import { ROLES } from '../../routes/roles'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, primaryButton, secondaryButton } from '../ui'
import SaveIndicator from './SaveIndicator'

const rupees = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`
const KINDS = ['consultation', 'procedure', 'medicine', 'investigation', 'other']

export default function BillingTab({ appt, onPaid }) {
  const { user } = useAuth()
  const [bill, setBill] = useState(null)
  const [draft, setDraft] = useState(null)
  const [mode, setMode] = useState('cash')
  const [waiving, setWaiving] = useState(null)
  const [error, setError] = useState('')

  const settled = bill && bill.payment_status !== 'unpaid'
  const save = useCallback(async (d) => setBill(await saveBill(appt.id, d)), [appt.id])
  const autosave = useAutosave(draft, save, { enabled: draft !== null && !settled })
  const { reset } = autosave

  const load = useCallback(
    (b) => {
      const d = { items: b.items, discount: b.discount }
      reset(d)
      setDraft(d)
      setBill(b)
    },
    [reset],
  )

  useEffect(() => {
    getBill(appt.id).then(load)
  }, [appt.id, load, appt.visit_type])

  if (!bill || !draft) return <p className="text-slate-500">Loading...</p>

  const setItem = (i, key, value) =>
    setDraft({ ...draft, items: draft.items.map((it, j) => (j === i ? { ...it, [key]: key === 'amount' ? Number(value) || 0 : value } : it)) })
  const subtotal = draft.items.reduce((s, i) => s + (Number(i.amount) || 0), 0)

  const settle = async (action) => {
    setError('')
    try {
      await autosave.flush()
      load(await action())
      onPaid?.()
    } catch (err) {
      setError(errorMessage(err, 'Could not update the bill'))
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {bill.fee_missing && !settled && (
        <p className="rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-800">
          No consultation fee is set for {bill.visit_type.replace('_', '-')} visits with this doctor, so it was filled in as ₹0.
          {user.role === ROLES.ADMIN && (
            <Link to={`/admin/doctors/${appt.doctor_id}`} className="ml-1 underline">
              Set fees
            </Link>
          )}
        </p>
      )}

      <section className={cardClass}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">Charges for this visit</h2>
          {!settled && <SaveIndicator autosave={autosave} />}
        </div>
        <table className="w-full text-sm">
          <tbody>
            {draft.items.map((it, i) => (
              <tr key={it.id ?? i} className="border-b border-slate-100">
                <td className="py-2 pr-2">
                  {settled ? (
                    it.description
                  ) : (
                    <input className={`${inputClass} py-1.5`} value={it.description} onChange={(e) => setItem(i, 'description', e.target.value)} />
                  )}
                  {it.auto && <span className="text-xs text-slate-400">Auto-filled from visit type</span>}
                </td>
                <td className="w-36 py-2 pr-2">
                  {settled ? (
                    <span className="capitalize text-slate-500">{it.kind}</span>
                  ) : (
                    <select className={`${inputClass} py-1.5`} value={it.kind} onChange={(e) => setItem(i, 'kind', e.target.value)}>
                      {KINDS.map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                <td className="w-32 py-2 text-right">
                  {settled ? (
                    rupees(it.amount)
                  ) : (
                    <input type="number" min={0} className={`${inputClass} py-1.5 text-right`} value={it.amount} onChange={(e) => setItem(i, 'amount', e.target.value)} />
                  )}
                </td>
                {!settled && (
                  <td className="w-8 text-right">
                    <button className="text-red-600" title="Remove" onClick={() => setDraft({ ...draft, items: draft.items.filter((_, j) => j !== i) })}>
                      x
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {!settled && (
          <button
            className="mt-2 text-sm text-brand-600 hover:underline"
            onClick={() => setDraft({ ...draft, items: [...draft.items, { description: '', amount: 0, kind: 'procedure' }] })}
          >
            + Add charge
          </button>
        )}

        <dl className="mt-4 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">Subtotal</dt>
            <dd>{rupees(subtotal)}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-slate-500">Discount</dt>
            <dd>
              {settled ? (
                rupees(bill.discount)
              ) : (
                <input type="number" min={0} className={`${inputClass} w-32! py-1 text-right`} value={draft.discount} onChange={(e) => setDraft({ ...draft, discount: Number(e.target.value) || 0 })} />
              )}
            </dd>
          </div>
          <div className="flex justify-between border-t border-slate-200 pt-2 text-base font-semibold">
            <dt>Total</dt>
            <dd>{rupees(Math.max(0, subtotal - draft.discount))}</dd>
          </div>
        </dl>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <section className={cardClass}>
        {settled ? (
          <p className="text-sm">
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${bill.payment_status === 'paid' ? 'bg-accent-100 text-accent-700' : 'bg-slate-100 text-slate-700'}`}>
              {bill.payment_status === 'paid' ? `Paid by ${bill.payment_mode}` : 'Waived'}
            </span>
            {bill.paid_at && <span className="ml-2 text-slate-500">{formatDate(bill.paid_at)} {formatTime(bill.paid_at)}</span>}
            {bill.waive_reason && <span className="ml-2 text-slate-500">Reason: {bill.waive_reason}</span>}
          </p>
        ) : waiving !== null ? (
          <div className="flex flex-wrap gap-2">
            <input className={`${inputClass} flex-1`} placeholder="Reason for waiving (required)" value={waiving} onChange={(e) => setWaiving(e.target.value)} />
            <button className={secondaryButton} onClick={() => setWaiving(null)}>
              Cancel
            </button>
            <button className={primaryButton} disabled={waiving.trim().length < 3} onClick={() => settle(() => waiveBill(appt.id, waiving.trim()))}>
              Waive
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <select className={`${inputClass} w-auto!`} value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Payment mode">
              <option value="cash">Cash</option>
              <option value="upi">UPI</option>
              <option value="card">Card</option>
              <option value="other">Other</option>
            </select>
            <button className={primaryButton} onClick={() => settle(() => payBill(appt.id, mode))}>
              Mark paid {rupees(Math.max(0, subtotal - draft.discount))}
            </button>
            <button className="text-sm text-slate-500 hover:underline" onClick={() => setWaiving('')}>
              Waive charges
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
