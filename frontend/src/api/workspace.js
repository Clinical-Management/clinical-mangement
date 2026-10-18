import api from './client'

export const getPrescription = (appointmentId) => api.get(`/appointments/${appointmentId}/prescription`).then((r) => r.data)

export const savePrescription = (appointmentId, payload) =>
  api.put(`/appointments/${appointmentId}/prescription`, payload).then((r) => r.data)

export const getBill = (appointmentId) => api.get(`/appointments/${appointmentId}/bill`).then((r) => r.data)

export const saveBill = (appointmentId, payload) => api.put(`/appointments/${appointmentId}/bill`, payload).then((r) => r.data)

export const payBill = (appointmentId, mode) => api.post(`/appointments/${appointmentId}/bill/pay`, { mode }).then((r) => r.data)

export const waiveBill = (appointmentId, reason) =>
  api.post(`/appointments/${appointmentId}/bill/waive`, { reason }).then((r) => r.data)

export const getPastVisits = (patientId, exclude) =>
  api.get(`/patients/${patientId}/visits`, { params: { exclude } }).then((r) => r.data)

export const getApprovedSummaries = (patientId) => api.get(`/patients/${patientId}/report-summaries`).then((r) => r.data)
