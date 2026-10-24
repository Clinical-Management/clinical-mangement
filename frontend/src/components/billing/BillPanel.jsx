import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  cancelBill,
  decideConcession,
  decideRefund,
  deliverReceipt,
  fetchReceiptPdf,
  getBill,
  listReceipts,
  listServices,
  requestRefund,
  saveBill,
  takePayment,
} from '../../api/billing'
import { useAuth } from '../../context/AuthContext'
import useAutosave from '../../hooks/useAutosave'
import { ROLES } from '../../routes/roles'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, primaryButton, secondaryButton } from '../ui'
import SaveIndicator from '../workspace/SaveIndicator'
import { GST_RATES, ITEM_KINDS, MODES, rupees, STATUS_STYLE, toPaise, toRupeeInput, VISIT_FEES } from './money'

const CONCESSIONS = [
  ['none', 'No concession'],
  ['senior', 'Senior citizen'],
  ['staff', 'Staff'],
  ['other', 'Other discount'],
  ['waiver', 'Waive the bill'],
]
const DELIVERY = [
  ['whatsapp', 'WhatsApp'],
  ['sms', 'SMS'],
  ['email', 'Email'],
  ['patient_app', 'Patient app'],
]

function toDraft(b) {
  return {
    items: b.items.filter((i) => i.id !== 'consultation').map((i) => ({ ...i, price: toRupeeInput(i.unit_price) })),
    fee: { basis: b.fee.basis, amount: b.fee.basis === 'custom' ? toRupeeInput(b.fee.amount) : '', reason: b.fee.reason ?? '' },
    concession: {
      type: b.concession.type,
      percent: b.concession.percent ?? '',
      amount: b.concession.percent == null ? toRupeeInput(b.concession.amount) : '',
      reason: b.concession.reason ?? '',
    },
  }
}

// Incomplete overrides (no reason yet) keep the last saved choice, so autosave never sends invalid data
function toPayload(d, saved) {
  const feeOk = d.fee.basis === 'auto' || (d.fee.reason.trim().length >= 3 && (d.fee.basis !== 'custom' || d.fee.amount !== ''))
  const c = d.concession
  const concessionOk = c.type === 'none' || (['senior', 'staff'].includes(c.type) ? true : c.reason.trim().length >= 3)
  const savedFee = saved.fee
  return {
    items: d.items
      .filter((i) => i.description.trim())
      .map((i) => ({ id: i.id, kind: i.kind, service_id: i.service_id ?? null, description: i.description.trim(), qty: Number(i.qty) || 1, unit_price: toPaise(i.price), tax_rate: Number(i.tax_rate) })),
    fee: feeOk
      ? { basis: d.fee.basis, amount: d.fee.basis === 'custom' ? toPaise(d.fee.amount) : null, reason: d.fee.basis === 'auto' ? null : d.fee.reason.trim() }
      : { basis: savedFee.basis, amount: savedFee.basis === 'custom' ? savedFee.amount : null, reason: savedFee.reason },
    concession: concessionOk
      ? {
          type: c.type,
          percent: ['senior', 'staff'].includes(c.type) ? (c.percent === '' ? null : Number(c.percent)) : c.type === 'other' && c.percent !== '' ? Number(c.percent) : null,
          amount: c.type === 'other' && c.percent === '' && c.amount !== '' ? toPaise(c.amount) : null,
          reason: c.reason.trim() || null,
        }
      : { type: saved.concession.type, percent: saved.concession.percent, amount: saved.concession.amount, reason: saved.concession.reason },
  }
}

async function openReceipt(id, fmt) {
  const url = URL.createObjectURL(await fetchReceiptPdf(id, fmt))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

function Receipts({ appt, refreshKey, canDeliver }) {
  const [receipts, setReceipts] = useState([])
  const [sent, setSent] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listReceipts(appt.id).then(setReceipts)
  }, [appt.id, refreshKey])

  if (!receipts.length) return null
  const send = async (r, channel) => {
    setError('')
    try {
      const res = await deliverReceipt(r.id, { channel })
      setSent({ ...res, number: r.number })
      if (res.share_url) window.open(res.share_url, '_blank', 'noopener')
    } catch (err) {
      setError(errorMessage(err, 'Could not send'))
    }
  }
  return (
    <section className={cardClass}>
      <h2 className="mb-3 text-sm font-semibold text-slate-800">Receipts</h2>
      <ul className="divide-y divide-slate-100 text-sm">
        {receipts.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              <span className="font-mono text-xs">{r.number}</span>
              <span className={`ml-2 font-medium ${r.kind === 'refund' ? 'text-red-700' : ''}`}>
                {r.kind === 'refund' ? '- ' : ''}
                {rupees(r.amount)}
              </span>
              <span className="ml-1 text-slate-500">
                {r.mode} | {formatDate(r.issued_at)} {formatTime(r.issued_at)}
              </span>
            </span>
            <span className="flex flex-wrap gap-2 text-xs">
              <button className="text-brand-600 hover:underline" onClick={() => openReceipt(r.id, 'a5')}>
                Print / PDF
              </button>
              <button className="text-brand-600 hover:underline" onClick={() => openReceipt(r.id, 'thermal')}>
                Thermal
              </button>
              {canDeliver &&
                DELIVERY.map(([channel, label]) => (
                  <button key={channel} className="text-brand-600 hover:underline" onClick={() => send(r, channel)}>
                    {label}
                  </button>
                ))}
            </span>
          </li>
        ))}
      </ul>
      {sent && (
        <p className={`mt-2 text-sm ${sent.status === 'failed' ? 'text-red-600' : 'text-accent-700'}`}>
          {sent.number}: {sent.detail}
        </p>
      )}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  )
}

/** The visit's bill: fee from the visit type, extra charges, concession, GST, payments, receipts, refunds. */
export default function BillPanel({ appt, onChange }) {
  const { user } = useAuth()
  const isAdmin = user.role === ROLES.ADMIN
  const frontDesk = [ROLES.ADMIN, ROLES.RECEPTIONIST].includes(user.role)
  const [bill, setBill] = useState(null)
  const [draft, setDraft] = useState(null)
  const [services, setServices] = useState([])
  const [payment, setPayment] = useState({ mode: 'cash', amount: '', reference: '' })
  const [refund, setRefund] = useState(null)
  const [receiptKey, setReceiptKey] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const editable = bill && ['unpaid', 'partial'].includes(bill.status)
  const save = useCallback(async (d) => setBill(await saveBill(appt.id, toPayload(d, bill))), [appt.id, bill])
  const autosave = useAutosave(draft, save, { enabled: draft !== null && editable })
  const { reset } = autosave

  const load = useCallback(
    (b) => {
      const d = toDraft(b)
      reset(d)
      setDraft(d)
      setBill(b)
      setPayment((p) => ({ ...p, amount: toRupeeInput(b.balance) }))
    },
    [reset],
  )

  useEffect(() => {
    getBill(appt.id).then(load)
    listServices().then(setServices).catch(() => {})
  }, [appt.id, appt.visit_type, load])

  if (!bill || !draft) return <p className="text-slate-500">Loading bill...</p>

  const act = async (fn) => {
    setBusy(true)
    setError('')
    try {
      await autosave.flush()
      const res = await fn()
      load(res.bill ?? res)
      setReceiptKey((k) => k + 1)
      onChange?.()
      return res
    } catch (err) {
      setError(errorMessage(err, 'Could not update the bill'))
    } finally {
      setBusy(false)
    }
  }

  const setItem = (i, patch) => setDraft({ ...draft, items: draft.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) })
  const addService = (id) => {
    const s = services.find((x) => x.id === id)
    if (s) setDraft({ ...draft, items: [...draft.items, { kind: s.kind, service_id: s.id, description: s.name, qty: 1, price: toRupeeInput(s.price), tax_rate: s.tax_rate }] })
  }
  const consult = bill.items.find((i) => i.id === 'consultation')
  const extra = bill.items.filter((i) => i.id !== 'consultation')
  const pending = bill.concession.status === 'pending'
  const net = bill.paid - bill.refunded

  return (
    <div className="space-y-5">
      {bill.fee_missing && editable && (
        <p className="rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-800">
          No consultation fee is set for this kind of visit with this doctor. Choose a fee below
          {isAdmin && (
            <>
              {' '}
              or{' '}
              <Link to={`/admin/doctors/${appt.doctor_id}`} className="underline">
                set the doctor&apos;s fees
              </Link>
            </>
          )}
          .
        </p>
      )}

      <section className={cardClass}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">
            Bill
            <span className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[bill.status]}`}>{bill.status}</span>
          </h2>
          {editable && <SaveIndicator autosave={autosave} />}
        </div>

        {/* consultation fee */}
        <div className="rounded-lg bg-slate-50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="font-medium text-slate-800">{consult.description}</span>
            <span className="font-semibold">{rupees(consult.amount)}</span>
          </div>
          <p className="text-xs text-slate-500">
            {draft.fee.basis === 'auto'
              ? `From the detected visit type (${bill.visit_type.replace('_', '-')})${bill.fee.source === 'specialty' ? ', specialty fee' : ''}`
              : `Changed: ${bill.fee.reason ?? ''}`}
          </p>
          {editable && !bill.payments.length && (
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              <select className={`${inputClass} py-1.5`} value={draft.fee.basis} onChange={(e) => setDraft({ ...draft, fee: { ...draft.fee, basis: e.target.value } })} aria-label="Consultation fee">
                <option value="auto">Fee from visit type</option>
                {VISIT_FEES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l} fee
                  </option>
                ))}
                <option value="custom">Custom amount</option>
              </select>
              {draft.fee.basis === 'custom' && (
                <input className={`${inputClass} py-1.5`} inputMode="decimal" placeholder="Amount (₹)" value={draft.fee.amount} onChange={(e) => setDraft({ ...draft, fee: { ...draft.fee, amount: e.target.value } })} />
              )}
              {draft.fee.basis !== 'auto' && (
                <input
                  className={`${inputClass} py-1.5 ${draft.fee.basis === 'custom' ? '' : 'sm:col-span-2'}`}
                  placeholder="Reason (required, logged)"
                  value={draft.fee.reason}
                  onChange={(e) => setDraft({ ...draft, fee: { ...draft.fee, reason: e.target.value } })}
                />
              )}
            </div>
          )}
        </div>

        {/* other charges */}
        <div className="mt-3 space-y-2">
          {(editable ? draft.items : extra).map((it, i) => (
            <div key={it.id ?? `new-${i}`} className="grid grid-cols-6 items-center gap-2 text-sm">
              {editable ? (
                <>
                  <input className={`${inputClass} col-span-6 py-1.5 sm:col-span-2`} placeholder="Description" value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} />
                  <select className={`${inputClass} col-span-2 py-1.5 sm:col-span-1`} value={it.kind} onChange={(e) => setItem(i, { kind: e.target.value })} aria-label="Kind">
                    {ITEM_KINDS.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                  <input className={`${inputClass} py-1.5`} type="number" min={1} value={it.qty} onChange={(e) => setItem(i, { qty: e.target.value })} aria-label="Quantity" />
                  <input className={`${inputClass} py-1.5 text-right`} inputMode="decimal" placeholder="₹" value={it.price} onChange={(e) => setItem(i, { price: e.target.value })} aria-label="Unit price" />
                  <div className="flex items-center gap-1">
                    <select className={`${inputClass} py-1.5`} value={it.tax_rate} onChange={(e) => setItem(i, { tax_rate: Number(e.target.value) })} aria-label="GST">
                      {GST_RATES.map((r) => (
                        <option key={r} value={r}>
                          GST {r}%
                        </option>
                      ))}
                    </select>
                    <button className="px-1 text-red-600" title="Remove" onClick={() => setDraft({ ...draft, items: draft.items.filter((_, j) => j !== i) })}>
                      x
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <span className="col-span-4">
                    {it.description}
                    {it.qty > 1 && ` x${it.qty}`}
                    {it.tax_rate > 0 && <span className="text-xs text-slate-500"> (GST {it.tax_rate}%)</span>}
                  </span>
                  <span className="col-span-2 text-right">{rupees(it.amount)}</span>
                </>
              )}
            </div>
          ))}
        </div>
        {editable && (
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {services.length > 0 && (
              <select className={`${inputClass} w-auto! py-1.5`} value="" onChange={(e) => addService(e.target.value)} aria-label="Add from price list">
                <option value="">+ Add from price list...</option>
                {services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} - {rupees(s.price)}
                  </option>
                ))}
              </select>
            )}
            <button className="text-sm text-brand-600 hover:underline" onClick={() => setDraft({ ...draft, items: [...draft.items, { kind: 'procedure', description: '', qty: 1, price: '', tax_rate: 0 }] })}>
              + Other charge
            </button>
          </div>
        )}

        {/* concession */}
        <div className="mt-4 border-t border-slate-100 pt-3">
          {editable ? (
            <div className="grid gap-2 sm:grid-cols-4">
              <select className={`${inputClass} py-1.5`} value={draft.concession.type} onChange={(e) => setDraft({ ...draft, concession: { type: e.target.value, percent: '', amount: '', reason: draft.concession.reason } })} aria-label="Concession">
                {CONCESSIONS.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
              {['senior', 'staff', 'other'].includes(draft.concession.type) && (
                <input className={`${inputClass} py-1.5`} type="number" min={0} max={100} placeholder={draft.concession.type === 'other' ? '% (or amount)' : 'Clinic preset %'} value={draft.concession.percent} onChange={(e) => setDraft({ ...draft, concession: { ...draft.concession, percent: e.target.value } })} aria-label="Percent" />
              )}
              {draft.concession.type === 'other' && draft.concession.percent === '' && (
                <input className={`${inputClass} py-1.5`} inputMode="decimal" placeholder="Amount ₹" value={draft.concession.amount} onChange={(e) => setDraft({ ...draft, concession: { ...draft.concession, amount: e.target.value } })} aria-label="Amount" />
              )}
              {draft.concession.type !== 'none' && (
                <input className={`${inputClass} py-1.5`} placeholder={['waiver', 'other'].includes(draft.concession.type) ? 'Reason (required)' : 'Note'} value={draft.concession.reason} onChange={(e) => setDraft({ ...draft, concession: { ...draft.concession, reason: e.target.value } })} />
              )}
            </div>
          ) : (
            bill.concession.type !== 'none' && <p className="text-sm text-slate-600">Concession: {CONCESSIONS.find(([v]) => v === bill.concession.type)?.[1]} {bill.concession.reason && `- ${bill.concession.reason}`}</p>
          )}
          {pending && (
            <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
              This concession needs an admin&apos;s approval before payment.
              {isAdmin && (
                <>
                  <button className="font-medium text-accent-700 hover:underline" onClick={() => act(() => decideConcession(appt.id, 'approve'))}>
                    Approve
                  </button>
                  <button className="font-medium text-red-700 hover:underline" onClick={() => act(() => decideConcession(appt.id, 'reject'))}>
                    Reject
                  </button>
                </>
              )}
            </div>
          )}
          {bill.concession.status === 'rejected' && <p className="mt-2 text-sm text-red-700">The concession was not approved.</p>}
        </div>

        {/* totals */}
        <dl className="mt-4 space-y-1 text-sm">
          {[
            ['Subtotal', bill.subtotal],
            bill.discount > 0 && ['Concession', -bill.discount],
            ...bill.tax_by_rate.flatMap((t) => [
              [`CGST ${t.rate_bp / 200}%`, t.cgst],
              [`SGST ${t.rate_bp / 200}%`, t.sgst],
            ]),
            bill.round_off !== 0 && ['Round off', bill.round_off],
          ]
            .filter(Boolean)
            .map(([label, value]) => (
              <div key={label} className="flex justify-between text-slate-600">
                <dt>{label}</dt>
                <dd>{value < 0 ? `- ${rupees(-value)}` : rupees(value)}</dd>
              </div>
            ))}
          <div className="flex justify-between border-t border-slate-200 pt-2 text-base font-semibold">
            <dt>Total</dt>
            <dd>{rupees(bill.total)}</dd>
          </div>
          {net !== 0 && (
            <div className="flex justify-between text-slate-600">
              <dt>Paid{bill.refunded ? ' (after refunds)' : ''}</dt>
              <dd>{rupees(net)}</dd>
            </div>
          )}
          <div className={`flex justify-between font-semibold ${bill.balance ? 'text-amber-800' : 'text-accent-700'}`}>
            <dt>Balance due</dt>
            <dd>{rupees(bill.balance)}</dd>
          </div>
        </dl>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* payment */}
      {frontDesk && editable && !pending && (
        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">{bill.total === 0 ? 'Nothing to pay' : 'Record a payment'}</h2>
          {bill.total === 0 ? (
            <button className={primaryButton} disabled={busy || bill.fee_missing} onClick={() => act(() => takePayment(appt.id, { mode: 'cash', amount: 0 }))}>
              Settle at no charge (issues a receipt)
            </button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <select className={`${inputClass} w-auto!`} value={payment.mode} onChange={(e) => setPayment({ ...payment, mode: e.target.value })} aria-label="Payment mode">
                {MODES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
              <input className={`${inputClass} w-32!`} inputMode="decimal" value={payment.amount} onChange={(e) => setPayment({ ...payment, amount: e.target.value })} aria-label="Amount (₹)" />
              {payment.mode !== 'cash' && (
                <input className={`${inputClass} w-44!`} placeholder="UPI ref / slip no." value={payment.reference} onChange={(e) => setPayment({ ...payment, reference: e.target.value })} />
              )}
              <button
                className={primaryButton}
                disabled={busy || bill.fee_missing || !toPaise(payment.amount)}
                onClick={() => act(() => takePayment(appt.id, { mode: payment.mode, amount: toPaise(payment.amount), reference: payment.reference.trim() || null })).then(() => setPayment((p) => ({ ...p, reference: '' })))}
              >
                Receive {rupees(toPaise(payment.amount))}
              </button>
              <span className="text-xs text-slate-500">Split payments: record each part separately.</span>
            </div>
          )}
        </section>
      )}

      <Receipts appt={appt} refreshKey={receiptKey} canDeliver={frontDesk} />

      {/* refunds and cancellation */}
      {frontDesk && (net > 0 || bill.refunds.length > 0 || (isAdmin && bill.status !== 'cancelled')) && (
        <section className={`${cardClass} space-y-3`}>
          <h2 className="text-sm font-semibold text-slate-800">Refunds{isAdmin && ' and cancellation'}</h2>
          {bill.refunds.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span>
                {rupees(r.amount)} by {r.mode} - {r.reason}
                <span className="ml-2 text-xs text-slate-500">
                  {r.status} {r.receipt_number && `(${r.receipt_number})`}
                </span>
              </span>
              {r.status === 'requested' && isAdmin && (
                <span className="flex gap-3 text-sm">
                  <button className="text-accent-700 hover:underline" onClick={() => act(() => decideRefund(appt.id, r.id, 'approve'))}>
                    Approve
                  </button>
                  <button className="text-red-700 hover:underline" onClick={() => act(() => decideRefund(appt.id, r.id, 'reject'))}>
                    Reject
                  </button>
                </span>
              )}
            </div>
          ))}
          {refund ? (
            <div className="flex flex-wrap items-center gap-2">
              <input className={`${inputClass} w-28!`} inputMode="decimal" placeholder="₹" value={refund.amount} onChange={(e) => setRefund({ ...refund, amount: e.target.value })} aria-label="Refund amount" />
              <select className={`${inputClass} w-auto!`} value={refund.mode} onChange={(e) => setRefund({ ...refund, mode: e.target.value })} aria-label="Refund mode">
                {MODES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
              <input className={`${inputClass} flex-1`} placeholder="Reason (required)" value={refund.reason} onChange={(e) => setRefund({ ...refund, reason: e.target.value })} />
              <button className={secondaryButton} onClick={() => setRefund(null)}>
                Cancel
              </button>
              <button
                className={primaryButton}
                disabled={busy || refund.reason.trim().length < 3 || !toPaise(refund.amount)}
                onClick={() => act(() => requestRefund(appt.id, { amount: toPaise(refund.amount), mode: refund.mode, reason: refund.reason.trim() })).then(() => setRefund(null))}
              >
                {isAdmin ? 'Refund' : 'Request refund'}
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-4 text-sm">
              {net > 0 && (
                <button className="text-brand-600 hover:underline" onClick={() => setRefund({ amount: toRupeeInput(net), mode: 'cash', reason: '' })}>
                  {isAdmin ? 'Refund' : 'Request a refund (admin approves)'}
                </button>
              )}
              {isAdmin && net === 0 && bill.status !== 'cancelled' && (
                <button
                  className="text-red-600 hover:underline"
                  onClick={() => {
                    const reason = window.prompt('Reason for cancelling this bill')
                    if (reason?.trim().length >= 3) act(() => cancelBill(appt.id, reason.trim()))
                  }}
                >
                  Cancel bill
                </button>
              )}
            </div>
          )}
          {bill.cancel_reason && <p className="text-sm text-red-700">Cancelled: {bill.cancel_reason}</p>}
        </section>
      )}
    </div>
  )
}
