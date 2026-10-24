import api from './client'

export const listStaff = () => api.get('/admin/users', { params: { staff: true, limit: 200 } }).then((r) => r.data)
export const createUser = (payload) => api.post('/admin/users', payload).then((r) => r.data)
export const updateUser = (id, changes) => api.patch(`/admin/users/${id}`, changes).then((r) => r.data)
export const resetUserMfa = (id) => api.post(`/admin/users/${id}/reset-mfa`)
export const resetUserPassword = (id, password) => api.post(`/admin/users/${id}/password`, { password })

export const getSecurity = () => api.get('/admin/security').then((r) => r.data)
export const saveSecurity = (payload) => api.put('/admin/security', payload).then((r) => r.data)

export const listAudit = (params) => api.get('/admin/audit', { params }).then((r) => r.data)
export const verifyAudit = () => api.get('/admin/audit/verify').then((r) => r.data)
export const exportAudit = (params) => api.get('/admin/audit/export', { params, responseType: 'blob' }).then((r) => r.data)
export const staffActivity = (params) => api.get('/admin/audit/activity', { params }).then((r) => r.data)
