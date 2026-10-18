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
    // Expired/invalid token: drop it and bounce to login (except on the login call itself,
    // on kiosk / patient-phone voicebot links, and on the prescription QR / patient-link pages, which have no login)
    const isLinkRequest = Boolean(err.config?.headers?.['X-History-Token'])
    const onPublicPage = /^\/(verify|rx)\//.test(window.location.pathname)
    if (err.response?.status === 401 && !err.config.url.endsWith('/auth/login') && !isLinkRequest) {
      localStorage.removeItem(TOKEN_KEY)
      if (!onPublicPage) window.location.assign('/login')
    }
    return Promise.reject(err)
  },
)

export default api
