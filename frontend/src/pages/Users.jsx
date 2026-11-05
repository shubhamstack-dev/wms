import React, { useState } from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Field, Note, Pill, Table, useLoad } from '../ui.jsx'

const ROLE_LIST = ['OPERATOR', 'SUPERVISOR', 'ADMIN']

export default function Users() {
  const { user, can, run } = useApp()
  const [list, reload] = useLoad(() => (can('reset') ? api.get('/users') : Promise.resolve([])), [])
  const [f, setF] = useState({ username: '', password: '', role: 'OPERATOR' })
  const [pw, setPw] = useState({ old_password: '', new_password: '' })

  const add = async () => {
    if (await run(() => api.post('/users', f), `User ${f.username} created`)) { setF({ username: '', password: '', role: 'OPERATOR' }); reload() }
  }
  const upd = async (u, body, msg) => { if (await run(() => api.put(`/users/${u.id}`, body), msg)) reload() }
  const resetPw = u => {
    const p = prompt(`New password for ${u.username} (min. 8 characters)`)
    if (p) upd(u, { password: p }, 'Password changed')
  }
  const del = async u => {
    if (confirm(`Delete user ${u.username}?`) && await run(() => api.del(`/users/${u.id}`), 'User deleted')) reload()
  }
  const changeOwn = async () => {
    if (await run(() => api.post('/auth/change-password', pw), 'Your password was changed')) setPw({ old_password: '', new_password: '' })
  }

  return (
    <div className="grid">
      <Card title="My password" sub={`Logged in as ${user.username} (${user.role})`}>
        <div className="row">
          <Field label="Current password"><input type="password" autoComplete="current-password" value={pw.old_password} onChange={e => setPw({ ...pw, old_password: e.target.value })} /></Field>
          <Field label="New password (min. 8)"><input type="password" autoComplete="new-password" value={pw.new_password} onChange={e => setPw({ ...pw, new_password: e.target.value })} /></Field>
          <button className="btn p" onClick={changeOwn} disabled={!pw.old_password || !pw.new_password}>Change password</button>
        </div>
      </Card>
      {can('reset') ? <>
        <Card title="Add user" sub="Operators confirm tasks; supervisors also create and release; admins can change everything and manage users">
          <div className="row">
            <Field label="Username"><input value={f.username} onChange={e => setF({ ...f, username: e.target.value })} /></Field>
            <Field label="Password (min. 8)"><input type="password" autoComplete="new-password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></Field>
            <Field label="Role"><select value={f.role} onChange={e => setF({ ...f, role: e.target.value })}>{ROLE_LIST.map(r => <option key={r}>{r}</option>)}</select></Field>
            <button className="btn p" onClick={add} disabled={!f.username || !f.password}>Add user</button>
          </div>
        </Card>
        <Card title="Users">
          <Table rows={list} empty="No users" cols={[
            { h: 'Username', r: u => <b>{u.username}</b> },
            { h: 'Role', r: u => <select style={{ width: 'auto' }} value={u.role} onChange={e => upd(u, { role: e.target.value }, 'Role changed')}>{ROLE_LIST.map(r => <option key={r}>{r}</option>)}</select> },
            { h: 'Status', r: u => <Pill tone={u.active ? 'g' : 'm'}>{u.active ? 'Active' : 'Disabled'}</Pill> },
            { h: '', r: u => u.id === user.id ? <span className="sub">this is you</span> : <div className="row nowrap">
              <button className="btn sm" onClick={() => resetPw(u)}>Set password</button>
              <button className="btn sm" onClick={() => upd(u, { active: !u.active }, u.active ? 'User disabled' : 'User enabled')}>{u.active ? 'Disable' : 'Enable'}</button>
              <button className="btn sm d" onClick={() => del(u)}>Delete</button></div> },
          ]} />
        </Card>
      </> : <Note>Only an administrator can add or change users.</Note>}
    </div>
  )
}
