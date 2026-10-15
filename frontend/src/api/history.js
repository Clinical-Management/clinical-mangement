import api from './client'

// Patient-side calls work with either a login or a kiosk/phone link token
const linkHeaders = (token) => (token ? { headers: { 'X-History-Token': token } } : {})

export const startHistory = (payload) => api.post('/history/sessions', payload).then((r) => r.data)

export const newHistoryLink = (id) => api.post(`/history/sessions/${id}/link`).then((r) => r.data)

export const getPatientView = (id, token) =>
  api.get(`/history/sessions/${id}/patient-view`, linkHeaders(token)).then((r) => r.data)

export const sendHistoryMessage = (id, token, text, input) =>
  api.post(`/history/sessions/${id}/messages`, { text, input }, linkHeaders(token)).then((r) => r.data)

export const setHistoryLanguage = (id, token, language) =>
  api.put(`/history/sessions/${id}/language`, { language }, linkHeaders(token)).then((r) => r.data)

export const finishHistory = (id, token) =>
  api.post(`/history/sessions/${id}/finish`, null, linkHeaders(token)).then((r) => r.data)

export const correctHistory = (id, token, text, input) =>
  api.post(`/history/sessions/${id}/correct`, { text, input }, linkHeaders(token)).then((r) => r.data)

export const submitHistory = (id, token) =>
  api.post(`/history/sessions/${id}/submit`, null, linkHeaders(token)).then((r) => r.data)

// Clinical (doctor / admin)
export const getHistory = (id) => api.get(`/history/sessions/${id}`).then((r) => r.data)

export const saveManualHistory = (id, fields) =>
  api.put(`/history/sessions/${id}/manual`, { fields }).then((r) => r.data)

export const submitManualHistory = (id) => api.post(`/history/sessions/${id}/manual/submit`).then((r) => r.data)

export const reviewHistoryField = (id, key, action, value) =>
  api.put(`/history/sessions/${id}/fields/${key}`, { action, value }).then((r) => r.data)

export const editHistorySummary = (id, summary) =>
  api.put(`/history/sessions/${id}/summary`, { summary }).then((r) => r.data)

export const listAlerts = () => api.get('/alerts').then((r) => r.data)

export const acknowledgeAlert = (id) => api.post(`/alerts/${id}/acknowledge`).then((r) => r.data)
