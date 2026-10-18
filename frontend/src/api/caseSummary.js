import api from './client'

const base = (id) => `/appointments/${id}/case-summary`

export const getCaseSummary = (id) => api.get(base(id)).then((r) => r.data)

export const generateCaseSummary = (id) => api.post(`${base(id)}/generate`).then((r) => r.data)

export const editCaseSummary = (id, sections) => api.put(base(id), { sections }).then((r) => r.data)

export const resolveSuggestion = (id, key, decision) =>
  api.post(`${base(id)}/suggestions/${key}/${decision}`).then((r) => r.data)

export const finalizeCaseSummary = (id) => api.post(`${base(id)}/finalize`).then((r) => r.data)

export const reopenCaseSummary = (id) => api.post(`${base(id)}/reopen`).then((r) => r.data)

export const getPrintablePrescription = (id) => api.get(`/appointments/${id}/prescription/print`).then((r) => r.data)
