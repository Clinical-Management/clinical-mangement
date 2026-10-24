import { useEffect, useState } from 'react'
import { addService, getBillingSettings, listServices, saveBillingSettings, updateService } from '../../api/billing'
import { GST_RATES, ITEM_KINDS, rupees, toPaise, VISIT_FEES } from '../../components/billing/money'
import { cardClass, errorMessage, inputClass, labelClass, primaryButton, secondaryButton } from '../../components/ui'

const NEW_SERVICE = { name: '', kind: 'procedure', price: '', tax_rate: 0 }

function PriceList() {
  const [services, setServices] = useState([])
  const [form, setForm] = useState(NEW_SERVICE)
  const [error, setError] = useState('')
  const load = () => listServices(true).then(setServices)
  useEffect(() => {
    load()
  }, [])

  const add = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await addService({ ...form, price: toPaise(form.price), tax_rate: Number(form.tax_rate) })
      setForm(NEW_SERVICE)
      load()
    } catch (err) {
      setError(errorMessage(err, 'Could not add'))
    }
  }
  const toggle = (s) => updateService(s.id, { ...s, active: !s.active }).then(load)

  return (
    <section className={cardClass}>
      <h2 className="mb-1 text-sm font-semibold text-slate-800">Price list</h2>
      <p className="mb-3 text-xs text-slate-500">Procedures, injections, dressings, in-clinic tests and dispensed medicines, picked when billing.</p>
      <ul className="mb-4 divide-y divide-slate-100 text-sm">
        {services.map((s) => (
          <li key={s.id} className={`flex items-center justify-between py-2 ${s.active ? '' : 'text-slate-400'}`}>
            <span>
              {s.name} <span className="text-xs text-slate-500">({ITEM_KINDS.find(([v]) => v === s.kind)?.[1]})</span>
            </span>
            <span className="flex items-center gap-4">
              {rupees(s.price)}
              {s.tax_rate > 0 && <span className="text-xs">+{s.tax_rate}% GST</span>}
              <button className="text-xs text-brand-600 hover:underline" onClick={() => toggle(s)}>
                {s.active ? 'Hide' : 'Show'}
              </button>
            </span>
          </li>
        ))}
        {!services.length && <li className="py-2 text-slate-500">No services yet.</li>}
      </ul>
      <form onSubmit={add} className="grid gap-2 sm:grid-cols-5">
        <input className={`${inputClass} sm:col-span-2`} required placeholder="Name, e.g. Nebulisation" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <select className={inputClass} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} aria-label="Kind">
          {ITEM_KINDS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <input className={inputClass} required inputMode="decimal" placeholder="Price ₹" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
        <div className="flex gap-2">
          <select className={inputClass} value={form.tax_rate} onChange={(e) => setForm({ ...form, tax_rate: e.target.value })} aria-label="GST">
            {GST_RATES.map((r) => (
              <option key={r} value={r}>
                GST {r}%
              </option>
            ))}
          </select>
          <button className={secondaryButton}>Add</button>
        </div>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  )
}

/** Admin: discount approval rules, presets, GST and rounding, specialty fee schedules and the price list. */
export default function BillingSettingsPage() {
  const [form, setForm] = useState(null)
  const [specialty, setSpecialty] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getBillingSettings().then(setForm)
  }, [])

  const save = async (e) => {
    e.preventDefault()
    setMessage('')
    setError('')
    try {
      setForm(await saveBillingSettings({ ...form, consultation_tax_rate: Number(form.consultation_tax_rate) }))
      setMessage('Saved. New bills use these settings; paid bills keep theirs.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  if (!form) return <p className="text-slate-500">Loading...</p>
  const num = (key, props = {}) => (
    <input type="number" className={inputClass} value={form[key]} onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} {...props} />
  )
  const setFee = (name, key, value) =>
    setForm({ ...form, specialty_fees: { ...form.specialty_fees, [name]: { ...form.specialty_fees[name], [key]: value === '' ? null : Number(value) } } })

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Billing settings</h1>
      {message && <p className="rounded-md bg-accent-50 px-4 py-3 text-sm text-accent-700">{message}</p>}
      {error && <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <form onSubmit={save} className="space-y-5">
        <section className={`${cardClass} grid gap-4 sm:grid-cols-3`}>
          <label>
            <span className={labelClass}>Concessions above this % need an admin</span>
            {num('approval_discount_percent', { min: 0, max: 100 })}
          </label>
          <label>
            <span className={labelClass}>Senior citizen concession %</span>
            {num('senior_percent', { min: 0, max: 100 })}
          </label>
          <label>
            <span className={labelClass}>Staff concession %</span>
            {num('staff_percent', { min: 0, max: 100 })}
          </label>
          <label>
            <span className={labelClass}>GST on consultation</span>
            <select className={inputClass} value={form.consultation_tax_rate} onChange={(e) => setForm({ ...form, consultation_tax_rate: e.target.value })}>
              {GST_RATES.map((r) => (
                <option key={r} value={r}>
                  {r === 0 ? 'Exempt (0%)' : `${r}%`}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pt-5 text-sm">
            <input type="checkbox" checked={form.round_to_rupee} onChange={(e) => setForm({ ...form, round_to_rupee: e.target.checked })} />
            Round totals to the nearest rupee
          </label>
          <p className="text-xs text-slate-500 sm:col-span-3">
            Waivers always need an admin. Doctors&apos; own fees, follow-up window and free follow-ups are set on each doctor&apos;s page; GSTIN and UPI ID are under Clinic
            letterhead.
          </p>
        </section>

        <section className={cardClass}>
          <h2 className="mb-1 text-sm font-semibold text-slate-800">Fees by specialty</h2>
          <p className="mb-3 text-xs text-slate-500">Used when a doctor of that specialty has no fee of their own (whole rupees). The specialty must match the doctor&apos;s specialization.</p>
          <div className="space-y-3">
            {Object.entries(form.specialty_fees).map(([name, fees]) => (
              <div key={name}>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">{name}</span>
                  <button
                    type="button"
                    className="text-xs text-red-600 hover:underline"
                    onClick={() => setForm({ ...form, specialty_fees: Object.fromEntries(Object.entries(form.specialty_fees).filter(([n]) => n !== name)) })}
                  >
                    Remove
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                  {VISIT_FEES.map(([key, label]) => (
                    <label key={key}>
                      <span className="text-xs text-slate-500">{label}</span>
                      <input type="number" min={0} className={`${inputClass} py-1.5`} value={fees[key] ?? ''} onChange={(e) => setFee(name, key, e.target.value)} />
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <input className={`${inputClass} w-64!`} placeholder="Specialty, e.g. Paediatrics" value={specialty} onChange={(e) => setSpecialty(e.target.value)} />
            <button
              type="button"
              className={secondaryButton}
              disabled={!specialty.trim()}
              onClick={() => {
                setForm({ ...form, specialty_fees: { ...form.specialty_fees, [specialty.trim()]: {} } })
                setSpecialty('')
              }}
            >
              Add specialty
            </button>
          </div>
        </section>

        <div className="flex justify-end">
          <button className={primaryButton}>Save billing settings</button>
        </div>
      </form>

      <PriceList />
    </div>
  )
}
