import React from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useApp } from './ctx.jsx'
import { api } from './api.js'
import { Logo } from './ui.jsx'
import Enterprise from './pages/Enterprise.jsx'
import Organisation from './pages/Organisation.jsx'
import Designer from './pages/Designer.jsx'
import Materials from './pages/Materials.jsx'
import Strategies from './pages/Strategies.jsx'
import Inbound from './pages/Inbound.jsx'
import Outbound from './pages/Outbound.jsx'
import CrossDock from './pages/CrossDock.jsx'
import Tasks from './pages/Tasks.jsx'
import Documents from './pages/Documents.jsx'
import Stock from './pages/Stock.jsx'
import Audit from './pages/Audit.jsx'
import Users from './pages/Users.jsx'

const NAV = [['/enterprise', 'Enterprise'], ['/organisation', 'Organisation'], ['/designer', 'Layout designer'],
  ['/materials', 'Materials'], ['/strategies', 'Strategies'], ['/inbound', 'Inbound'], ['/outbound', 'Outbound'],
  ['/crossdock', 'Cross-docking'], ['/tasks', 'Tasks & resources'], ['/documents', 'Documents'], ['/stock', 'Stock'], ['/audit', 'Audit'], ['/users', 'Users']]

export default function App() {
  const { whs, whId, setWhId, user, logout, settings, can, run, refreshWhs, bootError, loaded } = useApp()
  const loadDemo = async () => {
    if (!confirm('Replace ALL data in the database with the 3-warehouse demo?')) return
    if (await run(() => api.post('/admin/load-demo'), 'Demo loaded: WH01, WH02, XD01')) { await refreshWhs(); location.reload() }
  }
  if (bootError) return (
    <div className="boot card"><h3>Cannot reach the WMS middleware</h3>
      <button className="btn sm" style={{ float: 'right' }} onClick={logout}>Logout</button>
      <p className="sub">{bootError}</p>
      <p className="sub">Start the API (<span className="mono">uvicorn app.main:app --port 8000</span> in <span className="mono">backend/</span>) and check that MySQL is running, then reload.</p></div>
  )
  if (!loaded) return <div className="boot card"><div className="empty">Connecting to the WMS middleware…</div></div>
  return (
    <>
      <header className="top">
        <div className="hrow">
          <div className="brand"><Logo size={30} /><span className="brand-txt"><b>Aequm</b><small>Warehouse Management</small></span></div>
          {whs.length > 0 && <select style={{ width: 'auto', maxWidth: 290, fontWeight: 650 }} value={whId ?? ''} onChange={e => setWhId(Number(e.target.value))} aria-label="Active warehouse">
            {whs.map(w => <option key={w.id} value={w.id}>{w.code} · {w.name}{w.type === 'XD' ? ' (XD hub)' : ''}</option>)}
          </select>}
          <div className="spacer" />
          {can('reset') && settings.allow_reset && <button className="btn sm" onClick={loadDemo}>Load demo</button>}
          <span className="sub" title="Logged-in user">{user.username} · <b>{user.role}</b></span>
          <button className="btn sm" onClick={() => confirm('Log out?') && logout()}>Logout</button>
        </div>
        <nav className="tabs">{NAV.map(([p, l]) => <NavLink key={p} to={p} className={({ isActive }) => 'tab' + (isActive ? ' active' : '')}>{l}</NavLink>)}</nav>
      </header>
      <main>
        {!whs.length ? <div className="card empty">No warehouse yet. Create one with New warehouse below{settings.allow_reset ? ', or load the demo' : ''}.</div> : null}
        <Routes>
          <Route path="/" element={<Navigate to="/enterprise" replace />} />
          <Route path="/enterprise" element={<Enterprise />} />
          {whId && <>
            <Route path="/organisation" element={<Organisation key={whId} />} />
            <Route path="/designer" element={<Designer key={whId} />} />
            <Route path="/strategies" element={<Strategies key={whId} />} />
            <Route path="/inbound" element={<Inbound key={whId} />} />
            <Route path="/outbound" element={<Outbound key={whId} />} />
            <Route path="/crossdock" element={<CrossDock key={whId} />} />
            <Route path="/tasks" element={<Tasks key={whId} />} />
            <Route path="/documents" element={<Documents key={whId} />} />
            <Route path="/stock" element={<Stock key={whId} />} />
            <Route path="/audit" element={<Audit key={whId} />} />
          </>}
          <Route path="/materials" element={<Materials />} />
          <Route path="/users" element={<Users />} />
          <Route path="*" element={<Navigate to="/enterprise" replace />} />
        </Routes>
      </main>
    </>
  )
}
