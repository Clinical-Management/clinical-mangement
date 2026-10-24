import { useEffect, useState } from 'react'
import { fetchReceiptPdf, patientBills } from '../../api/billing'
import { listPatients } from '../../api/patients'
import { getClinicSettings } from '../../api/prescriptions'
import { rupees, STATUS_STYLE } from '../../components/billing/money'
import { cardClass, errorMessage, formatDate } from '../../components/ui'

const VISIT = { new: 'New visit', follow_up: 'Follow-up', returning: 'Returning' }

async function openReceipt(id) {
  const url = URL.createObjectURL(await fetchReceiptPdf(id))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

// Opens the patient's UPI app with the amount filled in; the clinic confirms the payment at the desk
const upiLink = (clinic, bill) =>
  `upi://pay?pa=${encodeURIComponent(clinic.upi_id)}&pn=${encodeURIComponent(clinic.name)}&am=${(bill.balance / 100).toFixed(2)}&cu=INR&tn=${encodeURIComponent(`Visit ${bill.date}`)}`

/** Patient app: bills, receipts and dues for every family profile. */
export default function PatientBillsPage() {
  const [groups, setGroups] = useState(null)
  const [clinic, setClinic] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getClinicSettings().then(setClinic).catch(() => {})
    listPatients()
      .then((profiles) => Promise.all(profiles.map(async (p) => ({ profile: p, bills: await patientBills(p.patient_id) }))))
      .then(setGroups)
      .catch((err) => setError(errorMessage(err, 'Could not load your bills')))
  }, [])

  if (error) return <p className="text-red-600">{error}</p>
  if (!groups) return <p className="text-slate-500">Loading...</p>
  const due = groups.flatMap((g) => g.bills).reduce((s, b) => s + b.balance, 0)

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Bills and receipts</h1>
      <div className={`${cardClass} flex items-center justify-between`}>
        <span className="text-sm text-slate-600">Pending dues</span>
        <span className={`text-2xl font-semibold ${due ? 'text-amber-800' : 'text-accent-700'}`}>{rupees(due)}</span>
      </div>
      {groups.map(({ profile, bills }) => (
        <section key={profile.patient_id} className="space-y-2">
          <h2 className="text-sm font-semibold text-slate-700">{profile.full_name}</h2>
          {!bills.length && <p className="text-sm text-slate-500">No bills yet.</p>}
          {bills.map((b) => (
            <div key={b.appointment_id} className={`${cardClass} space-y-2 py-4!`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm">
                  <b>{formatDate(b.date)}</b> - {b.doctor_name} ({VISIT[b.visit_type] ?? b.visit_type})
                </span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[b.status]}`}>{b.status}</span>
              </div>
              <p className="text-sm text-slate-600">
                Total {rupees(b.total)} | paid {rupees(b.paid)}
                {b.balance > 0 && <span className="font-medium text-amber-800"> | due {rupees(b.balance)}</span>}
              </p>
              {b.balance > 0 && clinic?.upi_id && (
                <a href={upiLink(clinic, b)} className="inline-block rounded-md bg-brand-gradient px-3 py-1.5 text-sm font-medium text-white">
                  Pay {rupees(b.balance)} by UPI
                </a>
              )}
              {b.balance > 0 && clinic?.upi_id && <p className="text-xs text-slate-500">After paying, show the UPI confirmation at the front desk to get your receipt.</p>}
              {b.receipts.length > 0 && (
                <div className="flex flex-wrap gap-3 text-sm">
                  {b.receipts.map((r) => (
                    <button key={r.id} className="text-brand-600 hover:underline" onClick={() => openReceipt(r.id)}>
                      {r.kind === 'refund' ? 'Refund' : 'Receipt'} {r.number} ({rupees(r.amount)})
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
