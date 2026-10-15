import axios from 'axios'

export const TOKEN_KEY = 'cm_token'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // Expired/invalid token: drop it and bounce to login (except on the login call itself)
    if (err.response?.status === 401 && !err.config.url.endsWith('/auth/login')) {
      localStorage.removeItem(TOKEN_KEY)
      window.location.assign('/login')
    }
    return Promise.reject(err)
  },
)

export default api
