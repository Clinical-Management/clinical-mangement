import api from './client'

export const listAppointments = (params) => api.get('/appointments', { params }).then((r) => r.data)

export const getAppointment = (id) => api.get(`/appointments/${id}`).then((r) => r.data)

export const bookAppointment = (payload) => api.post('/appointments', payload).then((r) => r.data)

export const registerWalkIn = (payload) => api.post('/appointments/walk-in', payload).then((r) => r.data)

export const getQueue = (params) => api.get('/appointments/queue', { params }).then((r) => r.data)

export const previewVisitType = (params) =>
  api.get('/appointments/visit-type-preview', { params }).then((r) => r.data)

export const checkIn = (id) => api.post(`/appointments/${id}/check-in`).then((r) => r.data)

export const reschedule = (id, payload) => api.post(`/appointments/${id}/reschedule`, payload).then((r) => r.data)

export const cancelAppointment = (id, reason) =>
  api.post(`/appointments/${id}/cancel`, { reason: reason || null }).then((r) => r.data)

export const updateStatus = (id, status) => api.post(`/appointments/${id}/status`, { status }).then((r) => r.data)

export const overrideVisitType = (id, payload) =>
  api.put(`/appointments/${id}/visit-type`, payload).then((r) => r.data)

export const clearVisitTypeOverride = (id) => api.delete(`/appointments/${id}/visit-type`).then((r) => r.data)

