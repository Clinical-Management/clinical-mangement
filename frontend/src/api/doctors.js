import api from './client'

export const listDoctors = () => api.get('/doctors').then((r) => r.data)

export const getDoctor = (id) => api.get(`/doctors/${id}`).then((r) => r.data)

export const saveSchedule = (id, payload) => api.put(`/doctors/${id}/schedule`, payload).then((r) => r.data)

export const getSlots = (id, date) => api.get(`/doctors/${id}/slots`, { params: { date } }).then((r) => r.data)

export const listLeaves = (id) => api.get(`/doctors/${id}/leaves`).then((r) => r.data)

export const addLeave = (id, payload) => api.post(`/doctors/${id}/leaves`, payload).then((r) => r.data)

export const deleteLeave = (id, leaveId) => api.delete(`/doctors/${id}/leaves/${leaveId}`)

export const createDoctor = (payload) => api.post('/admin/users', { ...payload, role: 'doctor' }).then((r) => r.data)

export const listHolidays = () => api.get('/holidays').then((r) => r.data)

export const addHoliday = (payload) => api.post('/holidays', payload).then((r) => r.data)

export const deleteHoliday = (id) => api.delete(`/holidays/${id}`)
