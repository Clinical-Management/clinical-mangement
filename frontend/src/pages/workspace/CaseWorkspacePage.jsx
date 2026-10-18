import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getAppointment, updateStatus } from '../../api/appointments'
import { getPatient } from '../../api/patients'
import { StatusBadge, VisitTypeBadge } from '../../components/appointments/Badges'
import { DiagnosisEditor, ExaminationEditor, NotesChangeLog } from '../../components/clinical/ClinicalNotesPanel'
import VitalsPanel from '../../components/clinical/VitalsPanel'
import VitalsTrends from '../../components/clinical/VitalsTrends'
import StartHistoryPanel from '../../components/history/StartHistoryPanel'
import { GENDERS, labelOf } from '../../components/patients/options'
import { errorBox, errorMessage, primaryButton, secondaryButton } from '../../components/ui'
import BillingTab from '../../components/workspace/BillingTab'
import OverviewTab from '../../components/workspace/OverviewTab'
import PastVisitsTab from '../../components/workspace/PastVisitsTab'
import PrescriptionTab from '../../components/workspace/PrescriptionTab'
import ReportsTab from '../../components/workspace/ReportsTab'
import { useAuth } from '../../context/AuthContext'
import useVisitNotes from '../../hooks/useVisitNotes'
import { APPOINTMENT_BASE, PATIENT_BASE } from '../../routes/roles'
import { HistoryWorkspace } from '../history/HistoryReviewPage'

const TABS = [
  ['overview', 'Overview'],
  ['history', 'History'],
  ['reports', 'Reports'],
  ['examination', 'Examination'],
  ['diagnosis', 'Diagnosis'],
  ['prescription', 'Prescription'],
  ['past', 'Past visits'],
  ['billing', 'Billing'],
]

export default function CaseWorkspacePage() {
  const { appointmentId } = useParams()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = TABS.some(([k]) => k === params.get('tab')) ? params.get('tab') : 'overview'

  const [appt, setAppt] = useState(null)
  const [patient, setPatient] = useState(null)
  const [notes, setNotes] = useVisitNotes(appointmentId)
  const [error, setError] = useState('')
  // Tabs stay mounted once opened, so unsaved typing, open sections and scroll survive switching
  const [visited, setVisited] = useState(() => new Set([tab]))
  const scrolls = useRef({})

  const reloadAppt = useCallback(() => getAppointment(appointmentId).then(setAppt), [appointmentId])

  useEffect(() => {
    getAppointment(appointmentId)
      .then((a) => {
        setAppt(a)
        return getPatient(a.patient_id).then(setPatient)
      })
      .catch((err) => setError(errorMessage(err, 'Could not open this visit')))
  }, [appointmentId])

  const switchTab = (key) => {
    scrolls.current[tab] = window.scrollY
    setVisited((v) => new Set(v).add(key))
    setParams({ tab: key }, { replace: true })
  }

  // Back to where the doctor was in that tab
  useLayoutEffect(() => {
    window.scrollTo(0, scrolls.current[tab] ?? 0)
  }, [tab])

  const move = async (status) => {
    if (status === 'completed' && !notes?.diagnoses.length && !window.confirm('No diagnosis has been recorded. Complete the visit anyway?')) return
    try {
      setAppt(await updateStatus(appt.id, status))
    } catch (err) {
      setError(errorMessage(err, 'Could not update the visit'))
    }
  }

  if (!appt || !patient || !notes) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Opening visit...</p>

  const allergies = patient.medical?.allergies ?? []
  const panel = (key, content) =>
    visited.has(key) && (
      <div key={key} hidden={tab !== key}>
        {content}
      </div>
    )

  return (
    <div className="space-y-4">
      <header className="sticky top-0 z-30 -mx-6 -mt-6 border-b border-slate-200 bg-white/95 px-6 pt-4 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-slate-800">
              <Link to={`${PATIENT_BASE[user.role]}/${patient.patient_id}`} className="hover:underline">
                {patient.full_name}
              </Link>
              <span className="ml-2 text-base font-normal text-slate-500">
                {patient.age ?? '?'} y, {labelOf(GENDERS, patient.gender)} | {patient.patient_id}
                {appt.token && ` | Token #${appt.token}`}
              </span>
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
              <VisitTypeBadge type={appt.visit_type} overridden={!!appt.visit_type_override} />
              <StatusBadge status={appt.status} />
              {appt.red_flag && <span className="rounded bg-red-600 px-1.5 py-0.5 font-medium text-white">Red flag: {appt.red_flag_labels}</span>}
              {allergies.length > 0 ? (
                <span className="rounded bg-red-100 px-1.5 py-0.5 font-medium text-red-800">
                  Allergies: {allergies.map((a) => a.substance).join(', ')}
                </span>
              ) : (
                <span className="text-slate-500">No known allergies</span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Link to={`${APPOINTMENT_BASE[user.role]}/${appt.id}`} className={secondaryButton}>
              Appointment
            </Link>
            {['waiting', 'with_voicebot'].includes(appt.status) && (
              <button className={primaryButton} onClick={() => move('in_consultation')}>
                Call in
              </button>
            )}
            {appt.status === 'in_consultation' && (
              <button className={primaryButton} onClick={() => move('completed')}>
                Complete visit
              </button>
            )}
          </div>
        </div>
        <nav className="-mb-px mt-3 flex gap-1 overflow-x-auto" role="tablist">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => switchTab(key)}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
                tab === key ? 'border-accent-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              {label}
              {key === 'diagnosis' && notes.diagnoses.length > 0 && (
                <span className="ml-1 rounded-full bg-brand-100 px-1.5 text-xs text-brand-700">{notes.diagnoses.length}</span>
              )}
            </button>
          ))}
        </nav>
      </header>

      {error && <p className={errorBox}>{error}</p>}

      {panel('overview', <OverviewTab appt={appt} patient={patient} />)}
      {panel(
        'history',
        appt.history_session_id ? <HistoryWorkspace sessionId={appt.history_session_id} embedded /> : <StartHistoryPanel appt={appt} />,
      )}
      {panel('reports', <ReportsTab appt={appt} patient={patient} />)}
      {panel(
        'examination',
        <div className="space-y-5">
          <ExaminationEditor appt={appt} notes={notes} onSaved={setNotes} />
          <VitalsPanel appt={appt} canRecord={!['cancelled', 'no_show'].includes(appt.status)} />
          <VitalsTrends patientId={patient.patient_id} />
        </div>,
      )}
      {panel(
        'diagnosis',
        <div className="space-y-5">
          <DiagnosisEditor appt={appt} notes={notes} onSaved={setNotes} />
          <NotesChangeLog notes={notes} />
        </div>,
      )}
      {panel('prescription', <PrescriptionTab appt={appt} notes={notes} onNotesSaved={setNotes} />)}
      {panel('past', <PastVisitsTab appt={appt} />)}
      {panel('billing', <BillingTab appt={appt} onPaid={reloadAppt} />)}
    </div>
  )
}
