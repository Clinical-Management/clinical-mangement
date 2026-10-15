import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { exportReport, fetchReportFile, getReport, replaceReportFile, updateReport } from '../../api/reports'
import { ACCEPT, formatSize, KIND_LABEL, REPORT_TYPES, saveOrShare, typeLabel } from '../../components/reports/reportMeta'
import { cardClass, errorBox, errorMessage, formatDate, formatTime, inputClass, labelClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE, ROLES } from '../../routes/roles'

/** Shows one version of the file. Files need the auth header, so they're loaded as blobs. */
function Viewer({ report, version, rendition }) {
  const [url, setUrl] = useState(null)
  const [error, setError] = useState('')
  const v = report.versions.find((x) => x.version === version)

  useEffect(() => {
    if (v.kind === 'dicom') return
    let objectUrl
    fetchReportFile(report.id, { version, rendition })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => setError('Could not load the file'))
    return () => objectUrl && URL.revokeObjectURL(objectUrl)
  }, [report.id, version, rendition, v.kind])

  if (v.kind === 'dicom') {
    return (
      <div className="rounded-lg bg-slate-50 p-6 text-sm text-slate-600">
        <p className="font-medium text-slate-800">DICOM image</p>
        <p>
          {[v.info.modality, v.info.body_part, v.info.study_description].filter(Boolean).join(' | ') || 'No study details'}
        </p>
        <p className="mt-2">Download the original to open it in a DICOM viewer, or export it as a PDF preview.</p>
      </div>
    )
  }
  if (error) return <p className="text-sm text-red-600">{error}</p>
  if (!url) return <p className="text-sm text-slate-500">Loading file...</p>
  return v.kind === 'pdf' ? (
    <iframe title="Report" src={url} className="h-[75vh] w-full rounded-lg border border-slate-200" />
  ) : (
    <img src={url} alt="Report" className="max-h-[75vh] rounded-lg border border-slate-200" />
  )
}

export default function ReportDetailPage() {
  const { patientId, reportId } = useParams()
  const { user } = useAuth()
  const libraryPath = `${PATIENT_BASE[user.role]}/${patientId}/reports`
  const canViewFiles = user.role !== ROLES.RECEPTIONIST

  const [report, setReport] = useState(null)
  const [version, setVersion] = useState(null)
  const [rendition, setRendition] = useState('processed')
  const [editing, setEditing] = useState(null)
  const [replacing, setReplacing] = useState(null) // { file, reason }
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getReport(reportId)
      .then((r) => {
        setReport(r)
        setVersion(r.current_version)
      })
      .catch((err) => setError(errorMessage(err, 'Could not load report')))
  }, [reportId])

  const run = async (action) => {
    setBusy(true)
    setError('')
    try {
      return await action()
    } catch (err) {
      setError(errorMessage(err, 'Action failed'))
    } finally {
      setBusy(false)
    }
  }

  if (!report) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Loading...</p>

  const v = report.versions.find((x) => x.version === version)
  const exportName = `${report.patient_id}-${report.report_type}-${report.report_date}.pdf`

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">{report.title || `${typeLabel(report.report_type)} report`}</h1>
          <p className="text-sm text-slate-500">
            <Link to={libraryPath} className="text-brand-600 hover:underline">
              {report.patient_name}'s reports
            </Link>{' '}
            | {typeLabel(report.report_type)} | {formatDate(report.report_date)} | ordered by {report.ordering_doctor}
            {report.visit_date && ` | visit ${formatDate(report.visit_date)}`}
          </p>
        </div>
        {canViewFiles && (
          <div className="flex flex-wrap gap-2">
            <button className={secondaryButton} disabled={busy} onClick={() => run(async () => saveOrShare(await exportReport(report.id), exportName, true))}>
              Share PDF
            </button>
            <button className={primaryButton} disabled={busy} onClick={() => run(async () => saveOrShare(await exportReport(report.id), exportName))}>
              Export PDF
            </button>
          </div>
        )}
      </div>

      {error && <p className={errorBox}>{error}</p>}

      <div className="grid gap-5 lg:grid-cols-3">
        <section className={`${cardClass} lg:col-span-2`}>
          {canViewFiles ? (
            <>
              {v.has_processed && (
                <div className="mb-3 inline-flex rounded-md border border-slate-300 p-0.5 text-sm">
                  {[
                    ['processed', 'Enhanced scan'],
                    ['original', 'Original photo'],
                  ].map(([key, label]) => (
                    <button key={key} onClick={() => setRendition(key)} className={`rounded px-3 py-1 ${rendition === key ? 'bg-brand-gradient text-white' : 'text-slate-600'}`}>
                      {label}
                    </button>
                  ))}
                </div>
              )}
              <Viewer report={report} version={version} rendition={v.has_processed ? rendition : 'original'} />
            </>
          ) : (
            <p className="text-sm text-slate-500">The file is available to the doctor and the patient. The upload was saved.</p>
          )}
        </section>

        <div className="space-y-5">
          <section className={cardClass}>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Details</h2>
              {!editing && (
                <button
                  className="text-sm text-brand-600 hover:underline"
                  onClick={() =>
                    setEditing({ report_type: report.report_type, report_date: report.report_date, ordering_doctor: report.ordering_doctor, title: report.title ?? '' })
                  }
                >
                  Edit tags
                </button>
              )}
            </div>
            {editing ? (
              <form
                className="space-y-3"
                onSubmit={async (e) => {
                  e.preventDefault()
                  const updated = await run(() => updateReport(report.id, { ...editing, title: editing.title || null }))
                  if (updated) {
                    setReport(updated)
                    setEditing(null)
                  }
                }}
              >
                <label className="block">
                  <span className={labelClass}>Type</span>
                  <select className={inputClass} value={editing.report_type} onChange={(e) => setEditing({ ...editing, report_type: e.target.value })}>
                    {REPORT_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className={labelClass}>Report date</span>
                  <input type="date" className={inputClass} value={editing.report_date} onChange={(e) => setEditing({ ...editing, report_date: e.target.value })} />
                </label>
                <label className="block">
                  <span className={labelClass}>Ordering doctor</span>
                  <input className={inputClass} required value={editing.ordering_doctor} onChange={(e) => setEditing({ ...editing, ordering_doctor: e.target.value })} />
                </label>
                <label className="block">
                  <span className={labelClass}>Title</span>
                  <input className={inputClass} value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
                </label>
                <div className="flex justify-end gap-2">
                  <button type="button" className={secondaryButton} onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                  <button className={primaryButton} disabled={busy}>
                    Save
                  </button>
                </div>
              </form>
            ) : (
              <dl className="space-y-1.5 text-sm">
                <div><dt className="inline text-slate-500">File: </dt><dd className="inline">{v.filename} ({KIND_LABEL[v.kind]}, {formatSize(v.size_bytes)})</dd></div>
                {v.info.pages && <div><dt className="inline text-slate-500">Pages: </dt><dd className="inline">{v.info.pages}</dd></div>}
                <div><dt className="inline text-slate-500">Uploaded: </dt><dd className="inline">{formatDate(v.uploaded_at)} {formatTime(v.uploaded_at)} by {v.uploaded_by_role}{v.source === 'camera' && ' (camera)'}</dd></div>
                {report.notes && <div><dt className="inline text-slate-500">Notes: </dt><dd className="inline">{report.notes}</dd></div>}
                {v.warnings.map((w) => (
                  <p key={w} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">⚠ {w}</p>
                ))}
              </dl>
            )}
          </section>

          <section className={cardClass}>
            <h2 className="mb-2 text-sm font-semibold text-slate-800">Versions</h2>
            <ul className="space-y-2 text-sm">
              {[...report.versions].reverse().map((x) => (
                <li key={x.version} className={`rounded-md border px-3 py-2 ${x.version === version ? 'border-accent-600 bg-accent-50' : 'border-slate-200'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <button className="text-left font-medium text-slate-800 hover:underline" onClick={() => setVersion(x.version)}>
                      v{x.version}
                      {x.version === report.current_version && ' (current)'}
                    </button>
                    {canViewFiles && (
                      <button
                        className="text-xs text-brand-600 hover:underline"
                        onClick={() => run(async () => saveOrShare(await fetchReportFile(report.id, { version: x.version, download: true }), x.filename))}
                      >
                        Download original
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">
                    {formatDate(x.uploaded_at)} by {x.uploaded_by_role}
                    {x.reason && ` | replaced because: ${x.reason}`}
                  </p>
                </li>
              ))}
            </ul>

            {replacing ? (
              <form
                className="mt-3 space-y-2"
                onSubmit={async (e) => {
                  e.preventDefault()
                  const updated = await run(() => replaceReportFile(report.id, { file: replacing.file, reason: replacing.reason }))
                  if (updated) {
                    setReport(updated)
                    setVersion(updated.current_version)
                    setReplacing(null)
                  }
                }}
              >
                <input type="file" accept={ACCEPT} required className="text-sm" onChange={(e) => setReplacing({ ...replacing, file: e.target.files[0] })} />
                <input className={inputClass} required placeholder="Why is it being replaced?" value={replacing.reason} onChange={(e) => setReplacing({ ...replacing, reason: e.target.value })} />
                <div className="flex justify-end gap-2">
                  <button type="button" className={secondaryButton} onClick={() => setReplacing(null)}>
                    Cancel
                  </button>
                  <button className={primaryButton} disabled={busy || !replacing.file}>
                    Upload new version
                  </button>
                </div>
              </form>
            ) : (
              <button className="mt-3 text-sm text-brand-600 hover:underline" onClick={() => setReplacing({ file: null, reason: '' })}>
                Replace file (keeps old versions)
              </button>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
