import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { useApp } from './ctx.jsx'

export const fmt = n => (Math.round((Number(n) || 0) * 1000) / 1000).toLocaleString('en-IN')
export const hm = t => (t ? String(t).slice(11, 16) : '—')
export const label = s => String(s || '').replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())

/** load data with a reload function: const [data, reload, err] = useLoad(() => api.get(...), [deps]) */
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setErr(null)
    fn().then(d => alive && setData(d)).catch(e => alive && setErr(e.message))
    return () => { alive = false }
  }, [...deps, tick])
  return [data, useCallback(() => setTick(t => t + 1), []), err]
}

const TONE = {
  OPEN: 'y', PLANNED: 'm', IN_PROCESS: 'b', IN_XDOCK: 'b', READY: 'y', CONFIRMED: 'g', DONE: 'g', SHIPPED: 'g', RECEIVED: 'g',
  COMPLETED: 'g', CREATED: 'm', RELEASED: 'y', TO_HUB: 'b', AT_HUB: 'v', IN_TRANSIT: 'b', WAVED: 'b', STAGED: 'v',
  AVAILABLE: 'g', BUSY: 'b', LOGGED_OFF: 'm', STORAGE: 'b', PICK: 'y', PUTAWAY: 'b', REPLEN: 'v', REARR: 'v', XDOCK: 'g',
}
export const Pill = ({ tone, children, title }) => <span className={'pill p-' + (tone || 'm')} title={title}>{children}</span>
export const Status = ({ s }) => <Pill tone={TONE[s]}>{label(s)}</Pill>
export const Kpi = ({ value, label: l, color }) => (
  <div className="kpi"><div className="v" style={color ? { color } : null}>{value}</div><div className="l">{l}</div></div>
)
export const Empty = ({ children }) => <div className="empty">{children}</div>
export const Note = ({ children, tone }) => <div className="note" style={tone ? { borderColor: `var(--${tone})` } : null}>{children}</div>

export function Card({ title, sub, actions, children, style }) {
  return (
    <section className="card" style={style}>
      {(title || actions) && (
        <div className="card-head">
          <div>{title && <h3>{title}</h3>}{sub && <div className="sub">{sub}</div>}</div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function SubNav({ tabs, value, onChange }) {
  return (
    <nav className="subnav">
      {tabs.map(([k, l, b]) => (
        <button key={k} className={'sn' + (k === value ? ' on' : '')} onClick={() => onChange(k)}>
          {l}{b ? <span className="b">{b}</span> : null}
        </button>
      ))}
    </nav>
  )
}

export function Drawer({ open, title, onClose, children }) {
  useEffect(() => {
    if (!open) return
    const h = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  return (
    <>
      <div className={'scrim' + (open ? ' on' : '')} onClick={onClose} />
      <aside className={'drawer' + (open ? ' on' : '')} aria-hidden={!open}>
        <div className="dhead"><h3>{title}</h3><button className="x" onClick={onClose} aria-label="Close">×</button></div>
        <div className="dbody">{open && children}</div>
      </aside>
    </>
  )
}

export const Field = ({ label: l, children, w }) => (
  <div className={w ? '' : 'f'} style={w ? { width: w } : null}><label>{l}</label>{children}</div>
)

export function Table({ cols, rows, empty = 'Nothing here yet', rowKey = r => r.id, max }) {
  const list = max ? (rows || []).slice(0, max) : rows || []
  return (
    <div className="tw">
      <table>
        <thead><tr>{cols.map((c, i) => <th key={i} className={c.num ? 'num' : ''} style={c.w ? { width: c.w } : null}>{c.h}</th>)}</tr></thead>
        <tbody>
          {list.length ? list.map((r, i) => (
            <tr key={rowKey(r) ?? i}>{cols.map((c, j) => <td key={j} className={(c.num ? 'num ' : '') + (c.mono ? 'mono' : '')}>{c.r(r)}</td>)}</tr>
          )) : <tr><td colSpan={cols.length} className="empty">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

/** options helper: rows → [[id, "CODE — name"]] */
export const opts = (rows, f = r => `${r.code} — ${r.name}`) => (rows || []).map(r => [r.id, f(r)])

function FieldInput({ f, value, onChange }) {
  if (f.t === 'sel') return (
    <select value={value ?? ''} onChange={e => onChange(f.num ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)}>
      {f.blank !== false && f.num && <option value="">— none —</option>}
      {f.o().map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  )
  if (f.t === 'multi') {
    const o = f.o(), cur = value || []
    return (
      <div className="checks">
        {o.length ? o.map(([v, l]) => (
          <label key={v} className="ck"><input type="checkbox" checked={cur.includes(v)}
            onChange={e => onChange(e.target.checked ? [...cur, v] : cur.filter(x => x !== v))} /> {l}</label>
        )) : <span className="faint">Create options first</span>}
      </div>
    )
  }
  if (f.t === 'bool') return <label className="ck"><input type="checkbox" checked={value !== false} onChange={e => onChange(e.target.checked)} /> {f.l}</label>
  return <input type={f.t === 'num' ? 'number' : 'text'} step="any" value={value ?? ''} style={f.t === 'code' ? { textTransform: 'uppercase' } : null}
    onChange={e => onChange(f.t === 'num' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)} />
}

/** Generic list + create/edit/delete card for any master-data endpoint. */
export function CrudCard({ title, sub, path, fields, extra = [], sing, onChanged, preset }) {
  const { can, run } = useApp()
  const [rows, reload] = useLoad(() => api.get(path), [path])
  const [edit, setEdit] = useState(null)
  const ed = can('setup') || (path.startsWith('/materials') && can('master'))
  const shown = fields.filter(f => !f.hideInTable)
  const save = async () => {
    const body = {}
    fields.forEach(f => { body[f.k] = edit.row[f.k] ?? f.d ?? (f.t === 'multi' ? [] : f.t === 'bool' ? true : f.t === 'num' ? 0 : '') })
    const r = await run(() => (edit.id ? api.put(`${path}/${edit.id}`, body) : api.post(path, body)), 'Saved')
    if (r) { setEdit(null); reload(); onChanged && onChanged() }
  }
  const del = async row => {
    if (!confirm(`Delete ${sing} ${row.code}?`)) return
    if (await run(() => api.del(`${path}/${row.id}`), 'Deleted')) { reload(); onChanged && onChanged() }
  }
  const cell = (f, r) => {
    const v = r[f.k]
    if (f.t === 'code') return <b className="mono">{v}</b>
    if (f.t === 'num') return fmt(v)
    if (f.t === 'bool') return v === false ? <span className="faint">No</span> : <span className="ok">Yes</span>
    if (f.t === 'sel') return f.o().find(o => String(o[0]) === String(v))?.[1] ?? '—'
    if (f.t === 'multi') { const o = f.o(); const l = (v || []).map(x => o.find(y => y[0] === x)?.[1]).filter(Boolean)
      return l.length ? l.map(x => <Pill key={x}>{x}</Pill>) : <span className="faint">—</span> }
    return v || '—'
  }
  return (
    <Card title={title} sub={sub} actions={ed && <button className="btn sm p" onClick={() => setEdit({ row: { ...(preset || {}) } })}>New {sing}</button>}>
      <Table rows={rows} empty={`No ${sing} yet`} cols={[
        ...shown.map(f => ({ h: f.l, num: f.t === 'num', r: r => cell(f, r) })),
        ...extra.map(([h, fn]) => ({ h, num: true, r: fn })),
        { h: '', r: r => ed && <span className="row nowrap"><button className="btn sm" onClick={() => setEdit({ id: r.id, row: { ...r } })}>Edit</button>
          <button className="btn sm d" onClick={() => del(r)}>Delete</button></span> },
      ]} />
      <Drawer open={!!edit} title={(edit?.id ? 'Edit ' : 'New ') + sing} onClose={() => setEdit(null)}>
        {edit && <>
          {fields.map(f => (
            <div key={f.k} style={{ marginBottom: 10 }}>
              {f.t !== 'bool' && <label>{f.l}</label>}
              <FieldInput f={f} value={edit.row[f.k] ?? f.d} onChange={v => setEdit(e => ({ ...e, row: { ...e.row, [f.k]: v } }))} />
            </div>
          ))}
          <button className="btn p" onClick={save}>{edit.id ? 'Save changes' : 'Create ' + sing}</button>
        </>}
      </Drawer>
    </Card>
  )
}
