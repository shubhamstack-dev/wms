import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, setToken, hasToken, onUnauthorized } from './api.js'
import Login from './pages/Login.jsx'

export const ROLES = {
  OPERATOR: ['confirm', 'count', 'move'],
  SUPERVISOR: ['confirm', 'count', 'move', 'create', 'release', 'adjust', 'master'],
  ADMIN: ['confirm', 'count', 'move', 'create', 'release', 'adjust', 'master', 'config', 'setup', 'reset'],
}
const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }) {
  const [user, setUser] = useState(null)          // { username, role } once logged in
  const [checking, setChecking] = useState(hasToken())
  const [whs, setWhs] = useState([])
  const [whId, setWhIdState] = useState(Number(localStorage.getItem('wms.wh')) || null)
  const [meta, setMeta] = useState({ gst_states: {} })
  const [settings, setSettings] = useState({ allow_reset: false })
  const [toastMsg, setToastMsg] = useState(null)
  const [bootError, setBootError] = useState(null)
  const [loaded, setLoaded] = useState(false)
  const tRef = useRef()

  const toast = useCallback(m => {
    setToastMsg(m); clearTimeout(tRef.current); tRef.current = setTimeout(() => setToastMsg(null), 3200)
  }, [])
  const setWhId = id => { localStorage.setItem('wms.wh', id); setWhIdState(id) }

  const logout = useCallback(() => { setToken(''); setUser(null); setLoaded(false) }, [])
  const loggedIn = (token, u) => { setToken(token); setUser(u) }

  useEffect(() => {
    onUnauthorized(() => { setUser(null); setLoaded(false); toast('Session ended. Please log in again.') })
    if (hasToken()) api.get('/auth/me').then(setUser).catch(() => setToken('')).finally(() => setChecking(false))
  }, [])

  const refreshWhs = useCallback(async () => {
    const list = await api.get('/warehouses')
    setWhs(list)
    setWhIdState(cur => (list.some(w => w.id === cur) ? cur : list[0]?.id ?? null))
    return list
  }, [])

  useEffect(() => {
    if (!user) return
    setBootError(null)
    Promise.all([refreshWhs(), api.get('/meta').then(setMeta), api.get('/settings').then(setSettings)])
      .then(() => setLoaded(true)).catch(e => user && setBootError(e.message))
  }, [user])

  /** run an API call, toast the result, return the value (or null on error) */
  const run = useCallback(async (fn, ok) => {
    try {
      const r = await fn()
      if (ok) toast(typeof ok === 'function' ? ok(r) : ok)
      return r ?? true
    } catch (e) { toast('⚠ ' + e.message); return null }
  }, [toast])

  const role = user?.role || 'OPERATOR'
  const can = a => (ROLES[role] || []).includes(a)
  const wh = whs.find(w => w.id === whId) || null
  const toastEl = <div className={'toast' + (toastMsg ? ' on' : '')} role="status">{toastMsg}</div>
  if (checking) return <div className="boot card"><div className="empty">Checking your login…</div></div>
  if (!user) return <><Login onLoggedIn={loggedIn} />{toastEl}</>
  return (
    <Ctx.Provider value={{ user, role, logout, settings, whs, wh, whId, setWhId, refreshWhs, meta, toast, run, can, bootError, loaded }}>
      {children}
      {toastEl}
    </Ctx.Provider>
  )
}
