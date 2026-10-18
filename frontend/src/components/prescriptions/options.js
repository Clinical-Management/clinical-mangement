import { fetchVersionPdf } from '../../api/prescriptions'

// Languages for the patient copy of a prescription
export const LANGS = [
  ['en', 'English'],
  ['hi', 'हिन्दी (Hindi)'],
  ['mr', 'मराठी (Marathi)'],
]

export async function openPdf(versionId, params) {
  const blob = await fetchVersionPdf(versionId, params)
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
