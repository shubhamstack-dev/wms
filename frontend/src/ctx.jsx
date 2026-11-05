import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, setApiRole } from './api.js'

export const ROLES = {
  OPERATOR: ['confirm', 'count', 'move'],
  SUPERVISOR: ['confirm', 'count', 'move', 'create', 'release', 'adjust', 'master'],
  ADMIN: ['confirm', 'count', 'move', 'create', 'release', 'adjust', 'master', 'config', 'setup', 'reset'],
}
const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }) {
  const [role, setRoleState] = useState(localStorage.getItem('wms.role') || 'ADMIN')
  const [whs, setWhs] = useState([])
  const [whId, setWhIdState] = useState(Number(localStorage.getItem('wms.wh')) || null)
  const [meta, setMeta] = useState({ gst_states: {} })
  const [toastMsg, setToastMsg] = useState(null)
  const [bootError, setBootError] = useState(null)
  const [loaded, setLoaded] = useState(false)
  const tRef = useRef()

  const toast = useCallback(m => {
    setToastMsg(m); clearTimeout(tRef.current); tRef.current = setTimeout(() => setToastMsg(null), 3200)
  }, [])
  const setRole = r => { setApiRole(r); localStorage.setItem('wms.role', r); setRoleState(r) }
  const setWhId = id => { localStorage.setItem('wms.wh', id); setWhIdState(id) }

  const refreshWhs = useCallback(async () => {
    const list = await api.get('/warehouses')
    setWhs(list)
    setWhIdState(cur => (list.some(w => w.id === cur) ? cur : list[0]?.id ?? null))
    return list
  }, [])

  useEffect(() => {
    setApiRole(role)
    Promise.all([refreshWhs(), api.get('/meta').then(setMeta)]).then(() => setLoaded(true)).catch(e => setBootError(e.message))
  }, [])

  /** run an API call, toast the result, return the value (or null on error) */
  const run = useCallback(async (fn, ok) => {
    try {
      const r = await fn()
      if (ok) toast(typeof ok === 'function' ? ok(r) : ok)
      return r ?? true
    } catch (e) { toast('⚠ ' + e.message); return null }
  }, [toast])

  const can = a => (ROLES[role] || []).includes(a)
  const wh = whs.find(w => w.id === whId) || null
  return (
    <Ctx.Provider value={{ role, setRole, whs, wh, whId, setWhId, refreshWhs, meta, toast, run, can, bootError, loaded }}>
      {children}
      <div className={'toast' + (toastMsg ? ' on' : '')} role="status">{toastMsg}</div>
    </Ctx.Provider>
  )
}
