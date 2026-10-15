import api from './client'

export const login = (email, password) =>
  api.post('/auth/login', { email, password }).then((r) => r.data)

export const register = (payload) => api.post('/auth/register', payload).then((r) => r.data)

export const fetchMe = () => api.get('/auth/me').then((r) => r.data)
