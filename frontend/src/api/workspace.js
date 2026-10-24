import api from './client'

export const getPrescription = (appointmentId) => api.get(`/appointments/${appointmentId}/prescription`).then((r) => r.data)

export const savePrescription = (appointmentId, payload) =>
  api.put(`/appointments/${appointmentId}/prescription`, payload).then((r) => r.data)

export const getPastVisits = (patientId, exclude) =>
  api.get(`/patients/${patientId}/visits`, { params: { exclude } }).then((r) => r.data)

export const getApprovedSummaries = (patientId) => api.get(`/patients/${patientId}/report-summaries`).then((r) => r.data)
