export const REPORT_TYPES = [
  { value: 'blood_test', label: 'Blood test' },
  { value: 'xray', label: 'X-ray' },
  { value: 'ct', label: 'CT' },
  { value: 'mri', label: 'MRI' },
  { value: 'ecg', label: 'ECG' },
  { value: 'ultrasound', label: 'Ultrasound' },
  { value: 'pathology', label: 'Pathology' },
  { value: 'other', label: 'Other' },
]

export const typeLabel = (value) => REPORT_TYPES.find((t) => t.value === value)?.label ?? value

export const KIND_LABEL = { pdf: 'PDF', jpeg: 'JPG', png: 'PNG', dicom: 'DICOM' }

export const ACCEPT = '.pdf,.jpg,.jpeg,.png,.dcm,application/pdf,image/jpeg,image/png,application/dicom'

export const formatSize = (bytes) =>
  bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`

/** Save a blob as a file, or hand it to the phone's share sheet when available. */
export async function saveOrShare(blob, filename, share = false) {
  const file = new File([blob], filename, { type: blob.type })
  if (share && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: filename })
      return
    } catch {
      // user cancelled the share sheet: fall through to download
    }
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
