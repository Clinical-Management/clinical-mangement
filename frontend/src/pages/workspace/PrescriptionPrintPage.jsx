import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getPrintablePrescription } from '../../api/caseSummary'
import Logo from '../../components/Logo'
import { GENDERS, labelOf } from '../../components/patients/options'
import { errorMessage, formatDate, primaryButton } from '../../components/ui'

/** Printable prescription (use the browser's Print / Save as PDF). */
export default function PrescriptionPrintPage() {
  const { appointmentId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getPrintablePrescription(appointmentId)
      .then(setData)
      .catch((err) => setError(errorMessage(err, 'Could not load the prescription')))
  }, [appointmentId])

  if (error) return <p className="p-8 text-red-600">{error}</p>
  if (!data) return <p className="p-8 text-slate-500">Loading...</p>

  const rx = data.prescription
  return (
    <div className="min-h-screen bg-slate-100 py-8 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-[210mm] justify-end gap-2 print:hidden">
        <button className={primaryButton} onClick={() => window.print()}>
          Print / Save as PDF
        </button>
      </div>
      <article className="mx-auto max-w-[210mm] bg-white px-10 py-8 text-sm text-slate-800 shadow print:max-w-none print:px-0 print:shadow-none">
        <header className="flex items-start justify-between border-b-4 border-[#039583] pb-4">
          <Logo />
          <div className="text-right">
            <p className="text-base font-semibold">{data.doctor_name}</p>
            {data.doctor_specialization && <p className="text-slate-500">{data.doctor_specialization}</p>}
          </div>
        </header>

        <section className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1">
          <p>
            <b>Patient:</b> {data.patient_name} ({data.patient_age ?? '?'} y, {labelOf(GENDERS, data.patient_gender)})
          </p>
          <p className="text-right">
            <b>Date:</b> {formatDate(data.visit_date)}
          </p>
          <p>
            <b>Patient ID:</b> {data.patient_id}
          </p>
          <p className="text-right">{data.token && `Token #${data.token}`}</p>
          <p className="col-span-2">
            <b>Allergies:</b> {data.allergies.length ? data.allergies.join(', ') : 'No known allergies'}
          </p>
        </section>

        {data.case_summary.length > 0 && (
          <section className="mt-5 space-y-2">
            {data.case_summary.map((s) => (
              <div key={s.key}>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{s.title}</h2>
                <p className="whitespace-pre-line">{s.text}</p>
              </div>
            ))}
          </section>
        )}

        <section className="mt-6">
          <h2 className="mb-2 text-2xl font-semibold text-[#023b77]">℞</h2>
          {rx.medicines.length === 0 ? (
            <p className="text-slate-500">No medicines prescribed.</p>
          ) : (
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-slate-300 text-xs uppercase text-slate-500">
                  <th className="py-1 pr-2">#</th>
                  <th className="py-1 pr-2">Medicine</th>
                  <th className="py-1 pr-2">Dose</th>
                  <th className="py-1 pr-2">Frequency</th>
                  <th className="py-1 pr-2">Duration</th>
                  <th className="py-1">Instructions</th>
                </tr>
              </thead>
              <tbody>
                {rx.medicines.map((m, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2">{i + 1}</td>
                    <td className="py-1.5 pr-2 font-medium">
                      {m.name}
                      {m.route && <span className="font-normal text-slate-500"> ({m.route})</span>}
                    </td>
                    <td className="py-1.5 pr-2">{m.dose}</td>
                    <td className="py-1.5 pr-2">{m.frequency}</td>
                    <td className="py-1.5 pr-2">{m.duration}</td>
                    <td className="py-1.5">{m.instructions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {rx.investigations.length > 0 && (
          <section className="mt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Investigations</h2>
            <p>{rx.investigations.map((i) => i.name + (i.notes ? ` (${i.notes})` : '')).join(', ')}</p>
          </section>
        )}
        {rx.advice && (
          <section className="mt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Advice</h2>
            <p className="whitespace-pre-line">{rx.advice}</p>
          </section>
        )}
        {rx.follow_up && (rx.follow_up.date || rx.follow_up.note) && (
          <section className="mt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Follow-up</h2>
            <p>{[rx.follow_up.date && formatDate(rx.follow_up.date), rx.follow_up.note].filter(Boolean).join(' - ')}</p>
          </section>
        )}

        <footer className="mt-12 flex justify-end">
          <div className="w-56 border-t border-slate-400 pt-1 text-center text-xs text-slate-500">{data.doctor_name}</div>
        </footer>
      </article>
    </div>
  )
}
