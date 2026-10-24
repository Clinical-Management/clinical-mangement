import api from './client'

// Patients get { access_token, user }; staff may get { mfa_required | mfa_setup_required, mfa_token }
export const login = (email, password) => api.post('/auth/login', { email, password }).then((r) => r.data)

export const register = (payload) => api.post('/auth/register', payload).then((r) => r.data)

export const fetchMe = () => api.get('/auth/me').then((r) => r.data)

export const refreshSession = () => api.post('/auth/refresh').then((r) => r.data)
export const logoutSession = () => api.post('/auth/logout')

// Two-step sign-in (authenticator app). mfaToken is passed mid-sign-in, omitted when signed in.
export const mfaVerify = (mfaToken, code) => api.post('/auth/mfa/verify', { mfa_token: mfaToken, code }).then((r) => r.data)
export const mfaSetup = (mfaToken) => api.post('/auth/mfa/setup', { mfa_token: mfaToken ?? null }).then((r) => r.data)
export const mfaEnable = (mfaToken, code) => api.post('/auth/mfa/enable', { mfa_token: mfaToken ?? null, code }).then((r) => r.data)
export const mfaDisable = (code) => api.post('/auth/mfa/disable', { code })
