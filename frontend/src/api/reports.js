import api from './client'

const form = (fields) => {
  const data = new FormData()
  Object.entries(fields).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') data.append(k, v)
  })
  return data
}

export const listReports = (patientId, params) =>
  api.get(`/patients/${patientId}/reports`, { params }).then((r) => r.data)

export const checkReportFile = (patientId, file) =>
  api.post(`/patients/${patientId}/reports/check`, form({ file })).then((r) => r.data)

export const uploadReport = (patientId, fields) =>
  api.post(`/patients/${patientId}/reports`, form(fields)).then((r) => r.data)

export const getReport = (id) => api.get(`/reports/${id}`).then((r) => r.data)

export const updateReport = (id, payload) => api.patch(`/reports/${id}`, payload).then((r) => r.data)

export const replaceReportFile = (id, fields) => api.post(`/reports/${id}/versions`, form(fields)).then((r) => r.data)

// Files need the auth header, so they are fetched as blobs rather than linked directly
export const fetchReportFile = (id, params) =>
  api.get(`/reports/${id}/file`, { params, responseType: 'blob' }).then((r) => r.data)

export const exportReport = (id) => api.get(`/reports/${id}/export`, { responseType: 'blob' }).then((r) => r.data)

export const exportReports = (patientId, reportIds) =>
  api.post(`/patients/${patientId}/reports/export`, { report_ids: reportIds }, { responseType: 'blob' }).then((r) => r.data)
