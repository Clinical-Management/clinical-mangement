import BillPanel from '../billing/BillPanel'

export default function BillingTab({ appt, onPaid }) {
  return (
    <div className="mx-auto max-w-3xl">
      <BillPanel appt={appt} onChange={onPaid} />
    </div>
  )
}
