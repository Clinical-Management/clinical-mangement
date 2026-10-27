import api from './client'

export const getFollowUp = (appointmentId) => api.get(`/appointments/${appointmentId}/follow-up`).then((r) => r.data.appointment)
export const nextFreeSlots = (doctorId, onOrAfter) => api.get(`/doctors/${doctorId}/next-free`, { params: { on_or_after: onOrAfter } }).then((r) => r.data)
export const followUpsDue = (params) => api.get('/follow-ups/due', { params }).then((r) => r.data)
export const listCallbacks = (includeClosed = false) => api.get('/follow-ups/callbacks', { params: { include_closed: includeClosed } }).then((r) => r.data)
export const recordCall = (appointmentId, payload) => api.post(`/follow-ups/callbacks/${appointmentId}`, payload).then((r) => r.data)

export const getReminderSettings = () => api.get('/reminders/settings').then((r) => r.data)
export const saveReminderSettings = (payload) => api.put('/reminders/settings', payload).then((r) => r.data)
export const listNotifications = (params) => api.get('/notifications', { params }).then((r) => r.data)
export const runNotificationsNow = () => api.post('/notifications/run').then((r) => r.data)

export const myInbox = () => api.get('/me/notifications').then((r) => r.data)
export const markInboxRead = () => api.post('/me/notifications/read')
export const setCommunication = (patientId, payload) => api.put(`/patients/${patientId}/communication`, payload).then((r) => r.data)

export const medicineRemindersOn = (versionId) => api.post(`/prescription-versions/${versionId}/medicine-reminders`).then((r) => r.data)
export const medicineRemindersOff = (versionId) => api.delete(`/prescription-versions/${versionId}/medicine-reminders`)
export const testReminder = (versionId, payload) => api.post(`/prescription-versions/${versionId}/test-reminders`, payload).then((r) => r.data)

// Public (no login): links in reminders
const pub = (id) => `/public/appointments/${id}`
export const publicAppointment = (id, t) => api.get(pub(id), { params: { t } }).then((r) => r.data)
export const publicConfirm = (id, t) => api.post(`${pub(id)}/confirm`, null, { params: { t } }).then((r) => r.data)
export const publicCancel = (id, t, reason) => api.post(`${pub(id)}/cancel`, { reason }, { params: { t } }).then((r) => r.data)
export const publicSlots = (id, t, date) => api.get(`${pub(id)}/slots`, { params: { t, date } }).then((r) => r.data)
export const publicReschedule = (id, t, payload) => api.post(`${pub(id)}/reschedule`, payload, { params: { t } }).then((r) => r.data)
