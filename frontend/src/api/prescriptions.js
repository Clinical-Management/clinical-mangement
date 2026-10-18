import api from './client'

export const searchMedicines = (q) => api.get('/medicines', { params: { q } }).then((r) => r.data)

export const finalizePrescription = (appointmentId, payload) =>
  api.post(`/appointments/${appointmentId}/prescription/finalize`, payload).then((r) => r.data)

export const listVersions = (appointmentId) => api.get(`/appointments/${appointmentId}/prescription/versions`).then((r) => r.data)

export const listDeliveries = (appointmentId) => api.get(`/appointments/${appointmentId}/prescription/deliveries`).then((r) => r.data)

export const fetchVersionPdf = (versionId, params) =>
  api.get(`/prescription-versions/${versionId}/pdf`, { params, responseType: 'blob' }).then((r) => r.data)

export const deliverVersion = (versionId, payload) => api.post(`/prescription-versions/${versionId}/deliver`, payload).then((r) => r.data)

export const listTemplates = () => api.get('/prescription-templates').then((r) => r.data)
export const saveTemplate = (payload) => api.post('/prescription-templates', payload).then((r) => r.data)
export const deleteTemplate = (id) => api.delete(`/prescription-templates/${id}`)

export const listFavourites = () => api.get('/prescription-favourites').then((r) => r.data)
export const addFavourite = (medicine) => api.post('/prescription-favourites', { medicine }).then((r) => r.data)
export const deleteFavourite = (id) => api.delete(`/prescription-favourites/${id}`)

export const getClinicSettings = () => api.get('/settings/clinic').then((r) => r.data)
export const saveClinicSettings = (payload) => api.put('/settings/clinic', payload).then((r) => r.data)

export const saveCredentials = (doctorId, payload) => api.put(`/doctors/${doctorId}/credentials`, payload).then((r) => r.data)
export const uploadSignature = (doctorId, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/doctors/${doctorId}/signature`, form)
}
export const fetchSignature = (doctorId) => api.get(`/doctors/${doctorId}/signature`, { responseType: 'blob' }).then((r) => r.data)

// Public (no login): QR verification and patient links
export const verifyPrescription = (publicId) => api.get(`/public/prescriptions/${publicId}`).then((r) => r.data)
export const getPatientLinkVersion = (publicId, token) =>
  api.get(`/public/prescriptions/${publicId}/patient`, { params: { token } }).then((r) => r.data)
export const fetchPatientLinkPdf = (publicId, token, lang) =>
  api.get(`/public/prescriptions/${publicId}/pdf`, { params: { token, lang }, responseType: 'blob' }).then((r) => r.data)
