import api from './client'

export const listPatients = (params) => api.get('/patients', { params }).then((r) => r.data)

export const getPatient = (patientId) => api.get(`/patients/${patientId}`).then((r) => r.data)

export const getFamily = (patientId) => api.get(`/patients/${patientId}/family`).then((r) => r.data)

export const createPatient = (payload) => api.post('/patients', payload).then((r) => r.data)

export const updatePatient = (patientId, payload) =>
  api.put(`/patients/${patientId}`, payload).then((r) => r.data)

export const updateMedical = (patientId, medical) =>
  api.put(`/patients/${patientId}/medical`, medical).then((r) => r.data)

export const updateConsent = (patientId, consent) =>
  api.put(`/patients/${patientId}/consent`, consent).then((r) => r.data)
