import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import * as authApi from '../api/auth'
import { TOKEN_KEY } from '../api/client'

const AuthContext = createContext(null)

const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'scroll', 'touchstart']
const CHECK_MS = 30_000

// Seconds left on the stored session token (0 if none or unreadable)
function secondsLeft() {
  try {
    const payload = JSON.parse(atob(localStorage.getItem(TOKEN_KEY).split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.exp - Date.now() / 1000
  } catch {
    return 0
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem(TOKEN_KEY)))
  const [endedReason, setEndedReason] = useState('')
  const lastActivity = useRef(0)

  // Restore the session from a stored token on first load
  useEffect(() => {
    if (!localStorage.getItem(TOKEN_KEY)) return
    authApi
      .fetchMe()
      .then(setUser)
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false))
  }, [])

  const startSession = useCallback((session) => {
    localStorage.setItem(TOKEN_KEY, session.access_token)
    setEndedReason('')
    setUser(session.user)
    return session.user
  }, [])

  /** Returns the user, or { mfa_required | mfa_setup_required, mfa_token } for staff. */
  const login = useCallback(
    async (email, password) => {
      const res = await authApi.login(email, password)
      return res.access_token ? startSession(res) : res
    },
    [startSession],
  )

  const logout = useCallback((reason = '') => {
    if (localStorage.getItem(TOKEN_KEY)) authApi.logoutSession().catch(() => {})
    localStorage.removeItem(TOKEN_KEY)
    setEndedReason(reason)
    setUser(null)
  }, [])

  // Sliding session: while the user is active the token is renewed; after the idle period it lapses
  // (staff: 30 minutes by default, set on the server) and the user is signed out.
  useEffect(() => {
    if (!user) return
    lastActivity.current = Date.now()
    const touch = () => (lastActivity.current = Date.now())
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, touch, { passive: true }))
    const timer = setInterval(async () => {
      const left = secondsLeft()
      if (left <= 0) return logout('Signed out after a period of inactivity.')
      const idleSeconds = (Date.now() - lastActivity.current) / 1000
      // renew once a third of the lifetime has passed, but only for someone actually using the app
      if (idleSeconds < left && left < 20 * 60 && idleSeconds < 5 * 60) {
        try {
          localStorage.setItem(TOKEN_KEY, (await authApi.refreshSession()).access_token)
        } catch {
          logout('Your session ended. Please sign in again.')
        }
      }
    }, CHECK_MS)
    return () => {
      clearInterval(timer)
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, touch))
    }
  }, [user, logout])

  return (
    <AuthContext.Provider value={{ user, loading, login, startSession, logout, endedReason }}>{children}</AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
