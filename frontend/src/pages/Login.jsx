import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Logo } from '../ui.jsx'

/** Login screen. While no user exists yet it creates the first administrator instead. */
export default function Login({ onLoggedIn }) {
  const [setup, setSetup] = useState(null)
  const [f, setF] = useState({ username: '', password: '', confirm: '' })
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/auth/status').then(s => setSetup(s.needs_setup)).catch(e => setErr(e.message)) }, [])
  const set = k => e => setF({ ...f, [k]: e.target.value })

  const submit = async e => {
    e.preventDefault(); setErr('')
    if (setup && f.password !== f.confirm) return setErr('The two passwords do not match')
    setBusy(true)
    try {
      const r = await api.post(setup ? '/auth/setup' : '/auth/login', { username: f.username, password: f.password })
      onLoggedIn(r.token, r.user)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <main className="login">
        <div className="login-head">
          <Logo size={64} />
          <h1>Aequm India Private Limited</h1>
          <p>Warehouse Management</p>
        </div>
        {setup === null && !err ? <div className="empty">Loading…</div> : (
          <form onSubmit={submit} className="login-form">
            <h2>{setup ? 'Create the administrator' : 'Sign in'}</h2>
            {setup && <p className="sub">No users exist yet. This first account becomes the administrator and can add everyone else.</p>}
            <div className="lf">
              <label htmlFor="u">Username</label>
              <input id="u" autoComplete="username" autoFocus value={f.username} onChange={set('username')} required />
            </div>
            <div className="lf">
              <label htmlFor="p">Password</label>
              <div className="pw">
                <input id="p" type={show ? 'text' : 'password'} autoComplete={setup ? 'new-password' : 'current-password'} value={f.password} onChange={set('password')} required />
                <button type="button" className="pw-t" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>{show ? 'Hide' : 'Show'}</button>
              </div>
            </div>
            {setup && <div className="lf">
              <label htmlFor="c">Repeat password</label>
              <input id="c" type={show ? 'text' : 'password'} autoComplete="new-password" value={f.confirm} onChange={set('confirm')} required />
              <span className="hint">At least 8 characters</span>
            </div>}
            {err && <div className="login-err" role="alert">{err}</div>}
            <button className="btn p login-btn" disabled={busy}>{busy ? 'Please wait…' : setup ? 'Create administrator' : 'Sign in'}</button>
          </form>
        )}
        <footer className="login-foot">© {new Date().getFullYear()} Aequm India Private Limited</footer>
      </main>
    </div>
  )
}
