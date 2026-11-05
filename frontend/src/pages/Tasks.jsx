import React, { useState } from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Kpi, Note, Pill, Status, SubNav, Table, fmt, hm, useLoad } from '../ui.jsx'

function Monitor({ m, reload }) {
  const { whId, can, run } = useApp()
  const act = async (p, msg) => { if (await run(() => api.post(`/warehouses/${whId}${p}`), msg)) reload() }
  const mx = Math.max(1, ...m.queues.map(q => q.waiting + q.in_process))
  return (
    <>
      <Card title="Queue workload" sub="Open warehouse orders per queue and how many resources are logged on to each"
        actions={can('release') && <button className="btn p" onClick={() => act('/resources/auto-assign', x => x.assigned ? `${x.assigned} WOs assigned` : 'No free resource or eligible WO')}>Auto-assign free resources</button>}>
        {m.queues.map(q => (
          <div key={q.code} className="qrow">
            <div><b className="mono">{q.code}</b><div className="sub">{q.name}</div></div>
            <div className="qb"><i style={{ width: `${q.in_process / mx * 100}%`, background: 'var(--accent)' }} /><i style={{ width: `${q.waiting / mx * 100}%`, background: 'var(--warn)' }} /></div>
            <div className="dim">{q.in_process} in process · {q.waiting} waiting</div>
            <div style={{ color: q.resources ? 'var(--ok)' : q.waiting ? 'var(--danger)' : 'var(--faint)' }}>{q.resources} resource{q.resources === 1 ? '' : 's'}</div>
          </div>))}
        <div className="legend"><span><i className="sw" style={{ background: 'var(--accent)' }} />In process</span><span><i className="sw" style={{ background: 'var(--warn)' }} />Waiting</span></div>
      </Card>
      <Card title="Resources" sub="Works like an RF device: log on → get next WO → confirm">
        <div className="rgrid">{m.resources.map(r => (
          <div key={r.id} className={'rcard ' + r.status}>
            <div className="row nowrap"><b className="mono">{r.code}</b><Status s={r.status} /></div>
            <div>{r.name}</div>
            <div className="sub">{r.type_name || '—'}{r.max_level ? ` · up to level ${r.max_level}` : ''}</div>
            <div className="sub">Queues: {r.queue_codes.join(', ') || 'all'}</div>
            {r.current && <Note><b className="mono">{r.current.number}</b> · {r.current.type} · {r.current.area}
              {r.current.lines.map((l, i) => <div key={i} className="mono" style={{ fontSize: 11.5 }}>{l.bin} {l.material} × {fmt(l.qty)}{l.done ? ' ✓' : ''}</div>)}</Note>}
            <div className="sub" style={{ marginTop: 6 }}>Today: <b>{r.done_today}</b> WOs{r.avg_minutes != null ? ` · avg ${r.avg_minutes} min` : ''} · {r.eligible_waiting} eligible waiting</div>
            {can('confirm') && <div className="row" style={{ marginTop: 8, gap: 5 }}>
              {r.status === 'LOGGED_OFF' ? <button className="btn sm p" onClick={() => act(`/resources/${r.id}/logon`, `${r.code} logged on`)}>Log on</button> : <>
                {r.status === 'AVAILABLE' && <button className="btn sm p" disabled={!r.eligible_waiting} onClick={() => act(`/resources/${r.id}/next`, x => x.wo ? `${x.wo} → ${r.code}` : 'No eligible WO')}>Get next WO</button>}
                {r.current && <button className="btn sm p" onClick={() => act(`/warehouse-orders/${r.current.id}/confirm`, `${r.current.number} confirmed`)}>Confirm {r.current.number}</button>}
                <button className="btn sm" onClick={() => act(`/resources/${r.id}/logoff`, `${r.code} logged off`)}>Log off</button></>}
            </div>}
          </div>))}</div>
        {!m.resources.length && <div className="empty">No resources — Organisation → Resources</div>}
      </Card>
    </>
  )
}

function Orders({ reloadAll }) {
  const { whId, can, run } = useApp()
  const [status, setStatus] = useState('open')
  const [rows, reload] = useLoad(() => api.get(`/warehouses/${whId}/warehouse-orders?status=${status}`), [whId, status])
  const [res] = useLoad(() => api.get(`/warehouses/${whId}/resources`), [whId])
  const act = async (p, body, msg) => { if (await run(() => api.post(`/warehouses/${whId}${p}`, body), msg)) { reload(); reloadAll() } }
  return (
    <Card title="Warehouse orders" sub="WTs of a document grouped per activity area, sorted along the path, split at the max size (Strategies)"
      actions={<select style={{ width: 'auto' }} value={status} onChange={e => setStatus(e.target.value)}>
        <option value="open">Open</option><option value="CONFIRMED">Confirmed</option><option value="">All</option></select>}>
      <Table rows={rows} empty="No warehouse orders" cols={[
        { h: 'WO', r: w => <b className="mono">{w.number}</b> }, { h: 'Doc', mono: true, r: w => w.doc_number }, { h: 'Type', r: w => <Status s={w.type} /> },
        { h: 'Area', mono: true, r: w => w.area }, { h: 'Queue', r: w => w.queue_code ? <span className="mono">{w.queue_code}</span> : <Pill tone="r">none</Pill> },
        { h: 'WTs', num: true, r: w => `${w.done}/${w.tasks}` },
        { h: 'Resource', r: w => w.status === 'OPEN' && can('release') ? (w.eligible.length ?
          <select style={{ width: 'auto', padding: '3px 6px' }} value="" onChange={e => e.target.value && act(`/warehouse-orders/${w.id}/assign`, { resource_id: Number(e.target.value) }, `${w.number} assigned`)}>
            <option value="">Assign…</option>{(res || []).filter(r => w.eligible.includes(r.id)).map(r => <option key={r.id} value={r.id}>{r.code}</option>)}</select>
          : <span className="faint">no eligible resource free</span>) : <span className="mono">{w.resource_code || '—'}</span> },
        { h: 'Status', r: w => <Status s={w.status} /> }, { h: 'Started', mono: true, r: w => hm(w.started_at) },
        { h: 'Min', num: true, r: w => w.minutes ?? '—' },
        { h: '', r: w => <span className="row nowrap">
          {w.status !== 'CONFIRMED' && can('confirm') && <button className="btn sm p" onClick={() => act(`/warehouse-orders/${w.id}/confirm`, undefined, `${w.number} confirmed`)}>Confirm</button>}
          {w.status === 'IN_PROCESS' && can('release') && <button className="btn sm" onClick={() => act(`/warehouse-orders/${w.id}/unassign`, undefined, 'Unassigned')}>Unassign</button>}</span> },
      ]} />
    </Card>
  )
}

function TaskList({ reloadAll }) {
  const { whId, can, run } = useApp()
  const [rows, reload] = useLoad(() => api.get(`/warehouses/${whId}/tasks?status=OPEN`), [whId])
  const [sel, setSel] = useState(new Set())
  const confirm = async () => { if (await run(() => api.post(`/warehouses/${whId}/tasks/confirm`, { ids: [...sel] }), x => `${x.confirmed} WTs confirmed`)) { setSel(new Set()); reload(); reloadAll() } }
  return (
    <Card title="Open warehouse tasks" sub="Every stock movement is a WT — putaway, pick, cross-dock"
      actions={can('confirm') && <button className="btn p" disabled={!sel.size} onClick={confirm}>Confirm selected ({sel.size})</button>}>
      <Table rows={rows} empty="No open tasks" cols={[
        { h: <input type="checkbox" checked={!!rows?.length && rows.every(t => sel.has(t.id))} onChange={e => setSel(new Set(e.target.checked ? rows.map(t => t.id) : []))} />,
          r: t => <input type="checkbox" checked={sel.has(t.id)} onChange={e => { const s = new Set(sel); e.target.checked ? s.add(t.id) : s.delete(t.id); setSel(s) }} /> },
        { h: 'WT', mono: true, r: t => String(t.wt_number).padStart(6, '0') }, { h: 'WO', mono: true, r: t => t.wo_number || '—' },
        { h: 'Type', r: t => <Status s={t.doc_type} /> }, { h: 'Material', mono: true, r: t => t.material_code },
        { h: 'Batch / serial', mono: true, r: t => t.tracking_no || '—' }, { h: 'Qty', num: true, r: t => fmt(t.qty) },
        { h: 'Source', mono: true, r: t => t.source_bin || '—' }, { h: 'Destination', mono: true, r: t => t.dest_bin || '—' },
      ]} />
    </Card>
  )
}

export default function Tasks() {
  const { whId } = useApp()
  const [tab, setTab] = useState('rm')
  const [m, reload] = useLoad(() => api.get(`/warehouses/${whId}/resource-monitor`), [whId])
  if (!m) return <Card><div className="empty">Loading…</div></Card>
  const k = m.kpi
  return (
    <>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        <Kpi value={k.open_tasks} label="Open tasks (WT)" /><Kpi value={k.open_wos} label="Open orders (WO)" />
        <Kpi value={k.unassigned} label="Unassigned WOs" color={k.unassigned ? 'var(--warn)' : null} />
        <Kpi value={<>{k.logged_on}<span className="dim" style={{ fontSize: 14 }}>/{k.resources}</span></>} label="Resources logged on" />
        <Kpi value={k.confirmed_today} label="WOs confirmed today" />
      </div>
      <SubNav value={tab} onChange={setTab} tabs={[['rm', 'Resource monitor'], ['wo', 'Warehouse orders'], ['wt', 'Warehouse tasks']]} />
      {tab === 'rm' && <Monitor m={m} reload={reload} />}{tab === 'wo' && <Orders reloadAll={reload} />}{tab === 'wt' && <TaskList reloadAll={reload} />}
    </>
  )
}
