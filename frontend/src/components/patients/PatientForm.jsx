import { useState } from 'react'
import { cardClass, inputClass, labelClass, primaryButton } from '../ui'
import { BLOOD_GROUPS, CONSENT_ITEMS, GENDERS, RELATIONSHIPS } from './options'

const TODAY = new Date().toISOString().slice(0, 10)

const EMPTY = {
  full_name: '',
  dob_mode: 'dob',
  date_of_birth: '',
  age: '',
  gender: '',
  blood_group: 'unknown',
  relationship: '',
  phone: '',
  email: '',
  address: { line1: '', line2: '', city: '', state: '', postal_code: '', country: '' },
  emergency_contact: { name: '', relationship: '', phone: '' },
  consent: { data_storage: false, voice_recording: false, ai_processing: false },
}

function fromPatient(p) {
  return {
    ...EMPTY,
    full_name: p.full_name,
    dob_mode: p.date_of_birth ? 'dob' : 'age',
    date_of_birth: p.date_of_birth ?? '',
    age: p.date_of_birth ? '' : String(p.age ?? ''),
    gender: p.gender,
    blood_group: p.blood_group,
    relationship: p.relationship ?? '',
    phone: p.phone,
    email: p.email ?? '',
    address: { ...EMPTY.address, ...nullsToEmpty(p.address) },
    emergency_contact: { ...EMPTY.emergency_contact, ...nullsToEmpty(p.emergency_contact) },
  }
}

const nullsToEmpty = (obj) =>
  Object.fromEntries(Object.entries(obj ?? {}).map(([k, v]) => [k, v ?? '']))

// Empty strings -> null; a group with no values at all -> null
const cleanGroup = (obj) => {
  const cleaned = Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, v.trim() || null]))
  return Object.values(cleaned).some(Boolean) ? cleaned : null
}

function toPayload(form, includeConsent) {
  const payload = {
    full_name: form.full_name.trim(),
    date_of_birth: form.dob_mode === 'dob' ? form.date_of_birth || null : null,
    age: form.dob_mode === 'age' && form.age !== '' ? Number(form.age) : null,
    gender: form.gender,
    blood_group: form.blood_group,
    relationship: form.relationship || null,
    phone: form.phone.trim(),
    email: form.email.trim() || null,
    address: cleanGroup(form.address),
    emergency_contact: cleanGroup(form.emergency_contact),
  }
  if (includeConsent) payload.consent = form.consent
  return payload
}

function Section({ title, children }) {
  return (
    <section className={cardClass}>
      <h2 className="mb-4 text-sm font-semibold text-slate-800">{title}</h2>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  )
}

function Field({ label, className = '', children }) {
  return (
    <label className={`block ${className}`}>
      <span className={labelClass}>{label}</span>
      {children}
    </label>
  )
}

/**
 * Registration / edit form for a patient record.
 * - `showRelationship`: 'required' | 'optional' | 'locked' | false
 * - consent checkboxes are shown only when creating (edits go through ConsentPanel)
 */
export default function PatientForm({ patient, defaults, showRelationship, submitLabel, onSubmit }) {
  const isCreate = !patient
  const [form, setForm] = useState(() => (patient ? fromPatient(patient) : { ...EMPTY, ...defaults }))
  const [submitting, setSubmitting] = useState(false)

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }))
  const setIn = (group, key, value) => setForm((f) => ({ ...f, [group]: { ...f[group], [key]: value } }))

  const input = (key, props = {}) => (
    <input className={inputClass} value={form[key]} onChange={(e) => set(key, e.target.value)} {...props} />
  )
  const groupInput = (group, key, props = {}) => (
    <input
      className={inputClass}
      value={form[group][key]}
      onChange={(e) => setIn(group, key, e.target.value)}
      {...props}
    />
  )
  const select = (key, options, props = {}) => (
    <select className={inputClass} value={form[key]} onChange={(e) => set(key, e.target.value)} {...props}>
      {props.placeholder !== undefined && <option value="">{props.placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await onSubmit(toPayload(form, isCreate))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <Section title="Basic details">
        <Field label="Full name *" className="sm:col-span-2">
          {input('full_name', { required: true, maxLength: 120 })}
        </Field>

        <div className="sm:col-span-2">
          <span className={labelClass}>Date of birth or age *</span>
          <div className="flex flex-wrap items-center gap-4">
            {[
              ['dob', 'Date of birth'],
              ['age', 'Age only (DOB unknown)'],
            ].map(([mode, label]) => (
              <label key={mode} className="flex items-center gap-2 text-sm text-slate-700">
                <input type="radio" checked={form.dob_mode === mode} onChange={() => set('dob_mode', mode)} />
                {label}
              </label>
            ))}
          </div>
          <div className="mt-2 max-w-xs">
            {form.dob_mode === 'dob'
              ? input('date_of_birth', { type: 'date', required: true, max: TODAY })
              : input('age', { type: 'number', min: 0, max: 130, required: true, placeholder: 'Age in years' })}
          </div>
        </div>

        <Field label="Gender *">{select('gender', GENDERS, { required: true, placeholder: 'Select' })}</Field>
        <Field label="Blood group">{select('blood_group', BLOOD_GROUPS)}</Field>

        {showRelationship && (
          <Field label={`Relationship to account holder${showRelationship === 'required' ? ' *' : ''}`}>
            {select('relationship', RELATIONSHIPS, {
              required: showRelationship === 'required',
              disabled: showRelationship === 'locked',
              placeholder: 'Select',
            })}
          </Field>
        )}
      </Section>

      <Section title="Contact">
        <Field label="Phone *">{input('phone', { type: 'tel', required: true, placeholder: '+91 98765 43210' })}</Field>
        <Field label="Email">{input('email', { type: 'email' })}</Field>
        <Field label="Address line 1" className="sm:col-span-2">
          {groupInput('address', 'line1')}
        </Field>
        <Field label="Address line 2" className="sm:col-span-2">
          {groupInput('address', 'line2')}
        </Field>
        <Field label="City">{groupInput('address', 'city')}</Field>
        <Field label="State">{groupInput('address', 'state')}</Field>
        <Field label="Postal code">{groupInput('address', 'postal_code')}</Field>
        <Field label="Country">{groupInput('address', 'country')}</Field>
      </Section>

      <Section title="Emergency contact">
        <Field label="Name">{groupInput('emergency_contact', 'name')}</Field>
        <Field label="Relationship">{groupInput('emergency_contact', 'relationship', { placeholder: 'e.g. Spouse' })}</Field>
        <Field label="Phone">{groupInput('emergency_contact', 'phone', { type: 'tel' })}</Field>
      </Section>

      {isCreate && (
        <section className={cardClass}>
          <h2 className="mb-1 text-sm font-semibold text-slate-800">Consent</h2>
          <p className="mb-4 text-xs text-slate-500">
            Voice and AI consent are needed before the voice assistant can be used. They can be changed later.
          </p>
          <div className="space-y-3">
            {CONSENT_ITEMS.map((item) => (
              <label key={item.key} className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  required={item.required}
                  checked={form.consent[item.key]}
                  onChange={(e) => setIn('consent', item.key, e.target.checked)}
                />
                <span>
                  <span className="font-medium text-slate-800">
                    {item.label}
                    {item.required && ' *'}
                  </span>
                  <span className="block text-slate-500">{item.description}</span>
                </span>
              </label>
            ))}
          </div>
        </section>
      )}

      <div className="flex justify-end">
        <button className={primaryButton} disabled={submitting}>
          {submitting ? 'Saving...' : submitLabel}
        </button>
      </div>
    </form>
  )
}
