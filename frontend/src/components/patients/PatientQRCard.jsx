import { QRCodeCanvas } from 'qrcode.react'
import { useRef } from 'react'

// The QR encodes just the Patient ID, so any scanner that types into the
// patient search box at reception opens the record directly.
export default function PatientQRCard({ patientId, size = 128, downloadable = true }) {
  const wrapper = useRef(null)

  const download = () => {
    const canvas = wrapper.current.querySelector('canvas')
    const link = document.createElement('a')
    link.href = canvas.toDataURL('image/png')
    link.download = `${patientId}.png`
    link.click()
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <div ref={wrapper} className="rounded-lg border border-slate-200 bg-white p-2">
        <QRCodeCanvas value={patientId} size={size} marginSize={1} />
      </div>
      <span className="font-mono text-sm font-semibold text-slate-700">{patientId}</span>
      {downloadable && (
        <button type="button" onClick={download} className="text-xs text-brand-600 hover:underline">
          Download QR
        </button>
      )}
    </div>
  )
}
