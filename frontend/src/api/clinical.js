import api from './client'

export const recordVitals = (appointmentId, payload) =>
  api.post(`/appointments/${appointmentId}/vitals`, payload).then((r) => r.data)

export const listVisitVitals = (appointmentId) => api.get(`/appointments/${appointmentId}/vitals`).then((r) => r.data)

export const getVitalsTrend = (patientId) => api.get(`/patients/${patientId}/vitals`).then((r) => r.data)

export const getNotes = (appointmentId) => api.get(`/appointments/${appointmentId}/notes`).then((r) => r.data)

export const saveExamination = (appointmentId, text, dictated) =>
  api.put(`/appointments/${appointmentId}/notes/examination`, { text, dictated }).then((r) => r.data)

export const addDiagnosis = (appointmentId, payload) =>
  api.post(`/appointments/${appointmentId}/notes/diagnoses`, payload).then((r) => r.data)

export const updateDiagnosis = (appointmentId, id, payload) =>
  api.patch(`/appointments/${appointmentId}/notes/diagnoses/${id}`, payload).then((r) => r.data)

export const removeDiagnosis = (appointmentId, id) =>
  api.delete(`/appointments/${appointmentId}/notes/diagnoses/${id}`).then((r) => r.data)

export const searchIcd10 = (q) => api.get('/icd10', { params: { q, limit: 12 } }).then((r) => r.data)

// Autosave of examination findings, private doctor notes and visit outcome
export const patchNotes = (appointmentId, changes) =>
  api.patch(`/appointments/${appointmentId}/notes`, changes).then((r) => r.data)
