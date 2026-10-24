import { Link } from 'react-router-dom'
import Logo from '../components/Logo'

const YEAR = new Date().getFullYear()

const STEPS = [
  ['1', 'Book and check in', 'Patients book online or walk in. The front desk checks them in and the live queue updates for everyone.'],
  ['2', 'History before the visit', 'A voice assistant takes the history in the patient’s language while they wait, and flags anything urgent.'],
  ['3', 'One consultation workspace', 'Vitals, reports with AI summaries, notes, diagnosis and the case summary in one tabbed view.'],
  ['4', 'Signed prescription, delivered', 'Safety-checked, signed with a QR code, and sent by WhatsApp, SMS or email in English, Hindi or Marathi.'],
]

const ROLES = [
  ['Doctors', 'Your queue, the patient’s full picture and a prescription in minutes.'],
  ['Front desk', 'Bookings, check-in, payments and printing from one screen.'],
  ['Admins', 'Doctors’ schedules, holidays, fees and the clinic letterhead.'],
  ['Patients', 'Book visits, share reports and keep every prescription on your phone.'],
]

const VITALS = [
  ['BP', '138/86'],
  ['Pulse', '98'],
  ['Temp', '101.2 °F', true],
  ['SpO2', '96%'],
]

/** Illustration: a consultation in the case workspace, with the signed prescription card on top. */
function ProductPreview() {
  return (
    <div className="relative mx-auto w-full max-w-xl pb-44 sm:pb-24" aria-hidden="true">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl shadow-brand-900/10 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-lg font-semibold text-slate-900">Asha Rao</p>
            <p className="text-xs text-slate-500">36 y, Female | Token #1</p>
          </div>
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">Allergy: Penicillin</span>
        </div>
        <div className="mt-4 flex gap-4 overflow-hidden border-b border-slate-200 text-xs text-slate-500">
          {['Overview', 'History', 'Reports', 'Diagnosis', 'Prescription'].map((t) => (
            <span key={t} className={`shrink-0 pb-2 ${t === 'Prescription' ? 'border-b-2 border-accent-600 font-medium text-brand-700' : ''}`}>
              {t}
            </span>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-4 gap-2">
          {VITALS.map(([label, value, high]) => (
            <div key={label} className={`rounded-lg border px-2 py-2 ${high ? 'border-amber-300 bg-amber-50' : 'border-slate-200'}`}>
              <p className="text-[10px] text-slate-500">{label}</p>
              <p className="text-sm font-semibold text-slate-800">{value}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 space-y-2">
          {[
            ['Azithromycin 500 mg', '1-0-0 | 3 days | after food'],
            ['Paracetamol 650 mg', 'SOS | 3 days'],
          ].map(([name, how]) => (
            <div key={name} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
              <span className="text-sm font-medium text-slate-800">{name}</span>
              <span className="text-xs text-slate-500">{how}</span>
            </div>
          ))}
          <p className="rounded-lg bg-accent-50 px-3 py-2 text-xs text-accent-700">✓ No allergy, interaction or dose warnings</p>
        </div>
      </div>

      <div className="absolute right-0 bottom-0 w-64 rounded-xl border border-slate-200 bg-white p-4 shadow-xl shadow-brand-900/15 sm:-right-6">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-900">Prescription v1</p>
          <span className="rounded-full bg-accent-100 px-2 py-0.5 text-xs font-medium text-accent-700">Signed</span>
        </div>
        <p className="mt-0.5 font-mono text-[11px] text-slate-500">RX-7QK2M9TXAB</p>
        <dl className="mt-3 space-y-1.5 text-sm">
          {[
            ['Safety checks', 'Passed'],
            ['Patient copy', 'Hindi'],
            ['Sent via', 'WhatsApp'],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <dt className="text-slate-500">{k}</dt>
              <dd className="text-slate-800">{v}</dd>
            </div>
          ))}
          <div className="flex justify-between border-t border-slate-100 pt-1.5 font-semibold">
            <dt className="text-slate-900">Follow-up</dt>
            <dd className="text-slate-900">In 5 days</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}

export default function Landing() {
  return (
    <div className="min-h-screen bg-white text-slate-800">
      <header className="sticky top-0 z-20 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Logo />
          <nav className="flex items-center gap-3 text-sm sm:gap-6">
            <a href="#how-it-works" className="hidden text-slate-600 hover:text-brand-700 sm:inline">
              How it works
            </a>
            <Link to="/login" className="font-medium text-slate-700 hover:text-brand-700">
              Sign in
            </Link>
            <Link to="/register" className="rounded-lg bg-brand-gradient px-4 py-2 font-medium text-white shadow-sm hover:opacity-95">
              Get started
            </Link>
          </nav>
        </div>
        <div className="h-1 bg-brand-gradient" />
      </header>

      <main>
        <section className="bg-gradient-to-b from-brand-50 to-white">
          <div className="mx-auto grid max-w-6xl items-center gap-14 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:py-24">
            <div>
              <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">Clinic management for doctors and front desks</p>
              <h1 className="mt-4 text-4xl leading-tight font-bold tracking-tight text-slate-900 sm:text-5xl">
                From check-in to prescription in <span className="text-brand-gradient">one place</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">
                Run the queue, take the patient&apos;s history before they reach the doctor, and send a signed prescription to their phone. No paper
                files, no retyping, no lost reports.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/register" className="rounded-lg bg-brand-gradient px-6 py-3 font-medium text-white shadow-md shadow-brand-900/20 hover:opacity-95">
                  Create a patient account
                </Link>
                <a href="#how-it-works" className="rounded-lg border border-slate-300 bg-white px-6 py-3 font-medium text-slate-700 hover:border-brand-200 hover:text-brand-700">
                  See how it works
                </a>
              </div>
              <p className="mt-5 text-sm text-slate-500">
                Clinic staff?{' '}
                <Link to="/login" className="font-medium text-brand-700 hover:underline">
                  Sign in
                </Link>{' '}
                with the account your admin created.
              </p>
            </div>
            <ProductPreview />
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">How it works</p>
            <h2 className="mt-2 max-w-2xl text-3xl font-bold tracking-tight text-slate-900">One visit, start to finish</h2>
            <ol className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map(([n, title, text]) => (
                <li key={n} className="rounded-xl border border-slate-200 p-6">
                  <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-gradient text-sm font-semibold text-white">{n}</span>
                  <h3 className="mt-4 font-semibold text-slate-900">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="bg-slate-50 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900">Built for everyone in the clinic</h2>
            <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {ROLES.map(([title, text]) => (
                <div key={title} className="rounded-xl border-t-4 border-accent-600 bg-white p-6 shadow-sm">
                  <h3 className="font-semibold text-slate-900">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="py-20">
          <div className="mx-auto max-w-4xl px-4 sm:px-6">
            <div className="rounded-2xl bg-brand-gradient px-8 py-12 text-center text-white">
              <h2 className="text-3xl font-bold tracking-tight">Your next visit, without the paperwork</h2>
              <p className="mx-auto mt-3 max-w-xl text-white/85">Create an account to book appointments and keep your reports and prescriptions together.</p>
              <div className="mt-7 flex flex-wrap justify-center gap-3">
                <Link to="/register" className="rounded-lg bg-white px-6 py-3 font-medium text-brand-700 hover:bg-brand-50">
                  Create a patient account
                </Link>
                <Link to="/login" className="rounded-lg border border-white/60 px-6 py-3 font-medium text-white hover:bg-white/10">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200 py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 text-sm text-slate-500 sm:px-6">
          <Logo compact />
          <p>© {YEAR} Clinical Management</p>
        </div>
      </footer>
    </div>
  )
}
