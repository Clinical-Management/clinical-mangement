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

// AI summaries
export const getReportSummary = (id) => api.get(`/reports/${id}/summary`).then((r) => r.data)

export const runReportSummary = (id) => api.post(`/reports/${id}/summary`).then((r) => r.data)

export const getPageCount = (id, version) => api.get(`/reports/${id}/pages`, { params: { version } }).then((r) => r.data.count)

export const fetchPageImage = (id, page, version) =>
  api.get(`/reports/${id}/pages/${page}`, { params: { version }, responseType: 'blob' }).then((r) => r.data)

export const editSummaryTest = (summaryId, testId, changes) =>
  api.patch(`/report-summaries/${summaryId}/tests/${testId}`, changes).then((r) => r.data)

export const addSummaryTest = (summaryId, row) => api.post(`/report-summaries/${summaryId}/tests`, row).then((r) => r.data)

export const removeSummaryTest = (summaryId, testId) =>
  api.delete(`/report-summaries/${summaryId}/tests/${testId}`).then((r) => r.data)

export const editSummaryText = (summaryId, changes) =>
  api.patch(`/report-summaries/${summaryId}/text`, changes).then((r) => r.data)

export const approveSummary = (summaryId) => api.post(`/report-summaries/${summaryId}/approve`).then((r) => r.data)

export const getSummaryTrends = (summaryId) => api.get(`/report-summaries/${summaryId}/trends`).then((r) => r.data)
