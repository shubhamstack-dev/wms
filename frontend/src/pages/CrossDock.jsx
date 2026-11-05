import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Drawer, Field, Kpi, Note, Status, SubNav, Table, fmt, hm, useLoad } from '../ui.jsx'
import { LineEditor } from './Inbound.jsx'

const FLOW = ['CREATED', 'RELEASED', 'TO_HUB', 'AT_HUB', 'IN_TRANSIT', 'COMPLETED']

function Planned({ xd, reload }) {
  const { whId, can, run } = useApp()
  const nav = useNavigate()
  const [mats] = useLoad(() => api.get('/materials'), [])
  const [f, setF] = useState({ from_party: '', to_party: '' })
  const [lines, setLines] = useState([])
  const act = async (id, a, msg) => { if (await run(() => api.post(`/warehouses/${whId}/crossdock-orders/${id}/${a}`), msg)) reload() }
  const create = async () => { if (await run(() => api.post(`/warehouses/${whId}/crossdock-orders`, { ...f, lines }), 'Cross-dock order created')) { setLines([]); reload() } }
  return (
    <>
      <Card title="Planned cross-docking" sub={`Customer known before arrival: ${xd.in_bin || '?'} (GR) → ${xd.out_bin || '?'} (GI), no putaway. Bins are set in Strategies.`}>
        <Table rows={xd.orders} empty="No cross-dock orders" cols={[
          { h: 'Order', r: o => <b className="mono">{o.number}</b> }, { h: 'Kind', r: o => <span className={'pill ' + (o.kind === 'TCD' ? 'p-v' : 'p-b')}>{o.kind === 'TCD' ? 'Transport' : 'Planned'}</span> },
          { h: 'From', r: o => o.from_party }, { h: 'To', r: o => o.to_party },
          { h: 'Lines', r: o => <span className="mono" style={{ fontSize: 12 }}>{o.lines.map(l => `${l.material_code} × ${fmt(l.qty)}`).join(', ')}</span> },
          { h: 'Tasks', mono: true, r: o => o.doc_number ? `${o.doc_number} · ${o.done}/${o.tasks}` : '—' },
          { h: 'Status', r: o => <Status s={o.status} /> }, { h: 'Received', mono: true, r: o => hm(o.received_at) },
          { h: 'Dwell', num: true, r: o => o.dwell_minutes != null ? `${o.dwell_minutes} min` : '—' },
          { h: '', r: o => <span className="row nowrap">
            {o.status === 'PLANNED' && can('release') && <button className="btn sm p" onClick={() => act(o.id, 'receive', `${o.number} received`)}>Receive</button>}
            {o.status === 'IN_XDOCK' && <><button className="btn sm" onClick={() => nav(`/documents?open=${o.document_id}`)}>Tasks</button>
              {can('confirm') && <button className="btn sm p" onClick={() => act(o.id, 'confirm-moves', 'Moves confirmed')}>Confirm moves</button>}</>}
            {o.status === 'READY' && can('release') && <button className="btn sm p" onClick={() => act(o.id, 'goods-issue', `${o.number} shipped`)}>Goods issue</button>}</span> },
        ]} />
      </Card>
      {can('create') && <Card title="New cross-dock order">
        <div className="row"><Field label="Supplier"><input value={f.from_party} onChange={e => setF({ ...f, from_party: e.target.value })} /></Field>
          <Field label="Ship to (customer)"><input value={f.to_party} onChange={e => setF({ ...f, to_party: e.target.value })} /></Field></div>
        <div style={{ marginTop: 9 }}><LineEditor mats={mats} lines={lines} setLines={setLines} /></div>
        <button className="btn p" style={{ marginTop: 10 }} disabled={!lines.length} onClick={create}>Create cross-dock order</button>
      </Card>}
    </>
  )
}

function Transfers() {
  const { whs, whId, can, run } = useApp()
  const [rows, reload] = useLoad(() => api.get('/transfers'), [])
  const [d, setD] = useState({ from_wh_id: whId, via_wh_id: null, to_wh_id: whs.find(w => w.id !== whId && w.type !== 'XD')?.id || null })
  const [mats] = useLoad(() => api.get(`/materials?wh=${d.from_wh_id}`), [d.from_wh_id])
  const [lines, setLines] = useState([])
  const [log, setLog] = useState(null)
  const act = async (t, a, msg) => { if (await run(() => api.post(`/transfers/${t.id}/${a}`), msg)) reload() }
  const create = async () => {
    if (await run(() => api.post('/transfers', { ...d, lines: lines.map(l => ({ material_id: l.material_id, qty: l.qty })) }), 'Transfer created')) { setLines([]); reload() }
  }
  const whSel = (k, none) => <select value={d[k] ?? ''} onChange={e => setD({ ...d, [k]: e.target.value ? Number(e.target.value) : null })}>
    {none && <option value="">{none}</option>}{whs.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}{w.type === 'XD' ? ' (XD hub)' : ''}</option>)}</select>
  const action = t => {
    if (!can('release')) return null
    const B = (a, l, msg) => <button className="btn sm p" onClick={() => act(t, a, msg)}>{l}</button>
    if (t.status === 'CREATED') return B('release', 'Release', 'Released')
    if (t.status === 'RELEASED') return <>{t.source_order && <span className="sub">{t.source_order.number} · {t.source_order.status} </span>}{B('pick-and-ship', 'Pick & ship now', `Shipped from ${t.from_code}`)}</>
    if (t.status === 'TO_HUB') return B('hub-receive', `Receive at ${t.via_code}`, 'Received at hub — no putaway')
    if (t.status === 'AT_HUB' && t.hub_xd?.status === 'IN_XDOCK') return B('hub-confirm', 'Confirm hub moves', 'Hub moves confirmed')
    if (t.status === 'AT_HUB' && t.hub_xd?.status === 'READY') return B('hub-dispatch', `Dispatch from ${t.via_code}`, `Dispatched to ${t.to_code}`)
    if (t.status === 'IN_TRANSIT') return B('receive', `Receive at ${t.to_code}`, 'Received — putaway created')
    return null
  }
  return (
    <>
      {can('create') && whs.length > 1 && <Card title="New stock transfer" sub="Source: pick & ship → optional cross-dock hub (straight onto the next truck, no putaway) → destination: receive & putaway">
        <div className="row"><Field label="From warehouse">{whSel('from_wh_id')}</Field><Field label="Via cross-dock hub">{whSel('via_wh_id', '— direct —')}</Field>
          <Field label="To warehouse">{whSel('to_wh_id')}</Field></div>
        <div style={{ marginTop: 9 }}><LineEditor mats={(mats || []).filter(m => m.stock > 0).map(m => ({ ...m, name: `${m.name} · ${fmt(m.stock)} available` }))}
          lines={lines} setLines={setLines} tracking={false} /></div>
        <button className="btn p" style={{ marginTop: 10 }} disabled={!lines.length} onClick={create}>Create transfer</button>
      </Card>}
      <Card title="Transfers" sub="Across all warehouses. Each step also works from the warehouses' own tabs (wave/pick, inbound receive) — the status follows automatically.">
        <Table rows={rows} empty="No transfers" cols={[
          { h: 'Transfer', r: t => <><b className="mono">{t.number}</b><div className="sub">{hm(t.created_at)}</div></> },
          { h: 'Route', r: t => { const stops = [t.from_code, t.via_code, t.to_code].filter(Boolean)
            const pos = { CREATED: 0, RELEASED: 0, TO_HUB: 0.5, AT_HUB: 1, IN_TRANSIT: t.via_code ? 1.5 : 0.5, COMPLETED: stops.length - 1 }[t.status]
            return <div className="route">{stops.map((s, i) => <React.Fragment key={i}>{i > 0 && <span className="dim">{pos === i - 0.5 ? '🚚' : '→'}</span>}
              <span className={'rstop ' + (pos === i ? 'here' : pos > i ? 'past' : '')}>{s}</span></React.Fragment>)}</div> } },
          { h: 'Materials', r: t => <span className="mono" style={{ fontSize: 12 }}>{t.lines.map(l => `${l.material_code} × ${fmt(l.qty)}`).join(', ')}</span> },
          { h: 'Status', r: t => <><Status s={t.status} /><div className="bar" style={{ width: 90 }}><i style={{ width: `${(FLOW.indexOf(t.status) + 1) / FLOW.length * 100}%` }} /></div></> },
          { h: 'Last event', r: t => { const e = t.events[t.events.length - 1]; return e ? <span className="sub">{e.message}</span> : '—' } },
          { h: '', r: t => <span className="row nowrap">{action(t)}<button className="btn sm" onClick={() => setLog(t)}>Log</button></span> },
        ]} />
      </Card>
      <Drawer open={!!log} title={`${log?.number} — event log`} onClose={() => setLog(null)}>
        {log?.events.map(e => <div key={e.id} style={{ padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
          <span className="mono dim">{e.ts.slice(0, 16).replace('T', ' ')}</span><div>{e.message}</div></div>)}
      </Drawer>
    </>
  )
}

function Opportunistic({ xd }) {
  return (
    <>
      <Card title="Open backorders" sub="Pick shortages in this warehouse — the next matching receipt goes straight to shipping (switch on in Strategies)">
        <Table rows={xd.backorders} rowKey={r => r.document + r.material_code} empty="No backorders" cols={[
          { h: 'Pick doc', mono: true, r: r => r.document }, { h: 'Material', mono: true, r: r => r.material_code },
          { h: 'Short', num: true, r: r => <span style={{ color: 'var(--danger)' }}>{fmt(r.qty)}</span> }]} />
      </Card>
      <Card title="Opportunistic cross-dock history">
        <Table rows={xd.opportunistic} empty="Nothing cross-docked yet" cols={[
          { h: 'ASN', mono: true, r: e => e.asn_number }, { h: 'Material', mono: true, r: e => e.material_code }, { h: 'Qty', num: true, r: e => fmt(e.qty) },
          { h: 'To bin', mono: true, r: e => e.to_bin }, { h: 'For', mono: true, r: e => e.pick_doc_number }, { h: 'When', mono: true, r: e => e.created_at?.slice(0, 16).replace('T', ' ') }]} />
      </Card>
    </>
  )
}

export default function CrossDock() {
  const { whId } = useApp()
  const [tab, setTab] = useState('pxd')
  const [xd, reload] = useLoad(() => api.get(`/warehouses/${whId}/crossdock-orders`), [whId])
  const [tr] = useLoad(() => api.get('/transfers'), [tab])
  if (!xd) return <Card><div className="empty">Loading…</div></Card>
  const shipped = xd.orders.filter(o => o.dwell_minutes != null)
  return (
    <>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        <Kpi value={xd.orders.filter(o => o.status === 'PLANNED').length} label="Planned XD orders" />
        <Kpi value={xd.orders.filter(o => ['IN_XDOCK', 'READY'].includes(o.status)).length} label="On the dock now" />
        <Kpi value={(tr || []).filter(t => t.status !== 'COMPLETED').length} label="Open transfers (all WH)" />
        <Kpi value={shipped.length ? Math.round(shipped.reduce((a, o) => a + o.dwell_minutes, 0) / shipped.length) + ' min' : '—'} label="Avg dock dwell" />
      </div>
      <SubNav value={tab} onChange={setTab} tabs={[['pxd', 'Planned cross-docking'], ['sto', 'Transfers & transport cross-docking'], ['opp', 'Opportunistic', xd.backorders.length]]} />
      {tab === 'pxd' && <Planned xd={xd} reload={reload} />}{tab === 'sto' && <Transfers />}{tab === 'opp' && <Opportunistic xd={xd} />}
    </>
  )
}
