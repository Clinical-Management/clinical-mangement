import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { listAppointments } from '../../api/appointments'
import { listDoctors } from '../../api/doctors'
import { getPatient } from '../../api/patients'
import { checkReportFile, uploadReport } from '../../api/reports'
import DocumentScanner from '../../components/reports/DocumentScanner'
import { ACCEPT, formatSize, REPORT_TYPES } from '../../components/reports/reportMeta'
import { cardClass, errorBox, errorMessage, formatDay, inputClass, labelClass, primaryButton, secondaryButton, todayISO } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE } from '../../routes/roles'

const OTHER = '__other__'

export default function UploadReportPage() {
  const { patientId } = useParams()
  const [params] = useSearchParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const base = `${PATIENT_BASE[user.role]}/${patientId}/reports`

  const [patient, setPatient] = useState(null)
  const [doctors, setDoctors] = useState([])
  const [visits, setVisits] = useState([])
  const [mode, setMode] = useState(null) // 'file' | 'camera'
  const [photo, setPhoto] = useState(null) // raw camera file waiting for the scanner
  const [files, setFiles] = useState(null) // { original, processed? }
  const [check, setCheck] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    report_type: '',
    report_date: todayISO(),
    doctor: '',
    other_doctor: '',
    appointment_id: params.get('appointment_id') ?? '',
    title: '',
    notes: '',
  })

  useEffect(() => {
    getPatient(patientId).then(setPatient).catch(() => {})
    listDoctors().then(setDoctors).catch(() => {})
    listAppointments({ patient_id: patientId }).then(setVisits).catch(() => {})
  }, [patientId])

  const chooseFiles = async (original, processed = null) => {
    setFiles({ original, processed })
    setCheck(null)
    setError('')
    try {
      // camera scans: judge quality on the enhanced copy the doctor will read
      setCheck(await checkReportFile(patientId, processed ? new File([processed], 'scan.jpg', { type: 'image/jpeg' }) : original))
    } catch (err) {
      setError(errorMessage(err, 'Could not check the file'))
    }
  }

  const orderingDoctor = form.doctor === OTHER ? form.other_doctor.trim() : form.doctor

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const report = await uploadReport(patientId, {
        file: files.original,
        processed: files.processed && new File([files.processed], 'enhanced.jpg', { type: 'image/jpeg' }),
        source: files.processed ? 'camera' : 'upload',
        report_type: form.report_type,
        report_date: form.report_date,
        ordering_doctor: orderingDoctor,
        appointment_id: form.appointment_id,
        title: form.title,
        notes: form.notes,
      })
      navigate(`${base}/${report.id}`)
    } catch (err) {
      setError(errorMessage(err, 'Upload failed'))
    } finally {
      setSaving(false)
    }
  }

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const fileOk = check?.ok

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">Upload report</h1>
        {patient && (
          <p className="text-sm text-slate-500">
            {patient.full_name} ({patient.patient_id}) |{' '}
            <Link to={base} className="text-brand-600 hover:underline">
              Back to reports
            </Link>
          </p>
        )}
      </div>

      {error && <p className={errorBox}>{error}</p>}

      <section className={cardClass}>
        <h2 className="mb-3 text-sm font-semibold text-slate-800">1. File</h2>
        {!files && !photo && (
          <div className="flex flex-wrap gap-2">
            <label className={`${primaryButton} cursor-pointer`}>
              Take photo of report
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files[0]) {
                    setMode('camera')
                    setPhoto(e.target.files[0])
                  }
                }}
              />
            </label>
            <label className={`${secondaryButton} cursor-pointer`}>
              Choose file (PDF, JPG, PNG, DICOM)
              <input
                type="file"
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => {
                  if (e.target.files[0]) {
                    setMode('file')
                    chooseFiles(e.target.files[0])
                  }
                }}
              />
            </label>
          </div>
        )}

        {photo && !files && (
          <DocumentScanner
            file={photo}
            onCancel={() => setPhoto(null)}
            onDone={({ original, processed }) => {
              setPhoto(null)
              chooseFiles(original, processed)
            }}
          />
        )}

        {files && (
          <div className="space-y-3">
            <p className="text-sm text-slate-700">
              <b>{files.original.name}</b> ({formatSize(files.original.size)})
              {mode === 'camera' && ' - scanned with camera; the original photo is kept as well'}
              <button
                type="button"
                className="ml-3 text-brand-600 hover:underline"
                onClick={() => {
                  setFiles(null)
                  setCheck(null)
                }}
              >
                Change
              </button>
            </p>
            {!check && <p className="text-sm text-slate-500">Checking file...</p>}
            {check?.errors.map((m) => (
              <p key={m} className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {m}
              </p>
            ))}
            {check?.warnings.map((m) => (
              <p key={m} className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
                ⚠ {m}
                {mode === 'camera' && ' You can retake the photo or upload anyway.'}
              </p>
            ))}
            {fileOk && check.warnings.length === 0 && (
              <p className="text-sm text-accent-700">
                ✓ File looks good
                {check.info.pages && ` (${check.info.pages} page${check.info.pages > 1 ? 's' : ''})`}
                {check.info.modality && ` (DICOM ${check.info.modality})`}
              </p>
            )}
          </div>
        )}
      </section>

      <form onSubmit={submit} className={`${cardClass} space-y-4`}>
        <h2 className="text-sm font-semibold text-slate-800">2. Details</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label>
            <span className={labelClass}>Report type *</span>
            <select className={inputClass} required value={form.report_type} onChange={set('report_type')}>
              <option value="">Select</option>
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>Report date *</span>
            <input type="date" className={inputClass} required max={todayISO()} value={form.report_date} onChange={set('report_date')} />
          </label>
          <label>
            <span className={labelClass}>Ordering doctor *</span>
            <select className={inputClass} required value={form.doctor} onChange={set('doctor')}>
              <option value="">Select</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.full_name}>
                  {d.full_name}
                </option>
              ))}
              <option value={OTHER}>Other doctor (outside this clinic)</option>
            </select>
          </label>
          {form.doctor === OTHER && (
            <label>
              <span className={labelClass}>Doctor's name *</span>
              <input className={inputClass} required maxLength={120} value={form.other_doctor} onChange={set('other_doctor')} />
            </label>
          )}
          <label>
            <span className={labelClass}>Visit</span>
            <select className={inputClass} value={form.appointment_id} onChange={set('appointment_id')}>
              <option value="">Not linked to a visit</option>
              {visits.map((v) => (
                <option key={v.id} value={v.id}>
                  {formatDay(v.date)} with {v.doctor_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>Title</span>
            <input className={inputClass} maxLength={120} placeholder="e.g. CBC, Chest PA view" value={form.title} onChange={set('title')} />
          </label>
        </div>
        <label className="block">
          <span className={labelClass}>Notes</span>
          <input className={inputClass} maxLength={1000} value={form.notes} onChange={set('notes')} />
        </label>
        <div className="flex justify-end">
          <button className={primaryButton} disabled={!fileOk || saving}>
            {saving ? 'Uploading...' : check?.warnings.length ? 'Upload anyway' : 'Upload report'}
          </button>
        </div>
      </form>
    </div>
  )
}
