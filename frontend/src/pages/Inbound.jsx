import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Field, Status, Table, fmt, opts, useLoad } from '../ui.jsx'

/** line editor shared by ASN, order and cross-dock forms */
export function LineEditor({ mats, lines, setLines, tracking = true }) {
  const [l, setL] = useState({ material_id: '', qty: 1, trk: '', expiry: '' })
  const mat = mats?.find(m => m.id === l.material_id)
  const code = id => mats?.find(m => m.id === id)?.code
  const add = () => { setLines([...lines, { ...l, expiry: l.expiry || null }]); setL(x => ({ ...x, trk: '' })) }
  const okTrk = !tracking || !mat || mat.tracking === 'NONE' || l.trk
  return (
    <>
      <div className="row">
        <Field label="Material"><select value={l.material_id} onChange={e => setL(x => ({ ...x, material_id: Number(e.target.value) }))}>
          <option value="">— choose —</option>{opts(mats).map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Field>
        <Field label="Qty" w={90}><input type="number" min={0} value={l.qty} onChange={e => setL(x => ({ ...x, qty: Number(e.target.value) }))} /></Field>
        {tracking && <Field label={mat?.tracking === 'SERIAL' ? 'Serial no.' : mat?.tracking === 'BATCH' ? 'Batch' : 'Not tracked'}>
          <input disabled={!mat || mat.tracking === 'NONE'} value={l.trk} onChange={e => setL(x => ({ ...x, trk: e.target.value }))} /></Field>}
        {tracking && <Field label="Expiry" w={150}><input type="date" disabled={mat?.tracking !== 'BATCH'} value={l.expiry} onChange={e => setL(x => ({ ...x, expiry: e.target.value }))} /></Field>}
        <button className="btn" disabled={!l.material_id || !(l.qty > 0) || !okTrk} onClick={add}>Add line</button>
      </div>
      <div style={{ marginTop: 9 }}>{lines.length ? lines.map((x, i) => <span key={i} className="pill p-b">{code(x.material_id)} × {fmt(x.qty)}{x.trk ? ' · ' + x.trk : ''}
        <a href="#" style={{ color: 'inherit', marginLeft: 4 }} onClick={e => { e.preventDefault(); setLines(lines.filter((_, j) => j !== i)) }}>✕</a></span>)
        : <span className="faint">No lines yet</span>}</div>
    </>
  )
}

export default function Inbound() {
  const { whId, can, run } = useApp()
  const nav = useNavigate()
  const [asns, reload] = useLoad(() => api.get(`/warehouses/${whId}/asns`), [whId])
  const [mats] = useLoad(() => api.get('/materials'), [])
  const [f, setF] = useState({ vendor: '', eta: '' })
  const [lines, setLines] = useState([])
  const code = id => mats?.find(m => m.id === id)?.code
  const receive = async a => {
    const r = await run(() => api.post(`/warehouses/${whId}/asns/${a.id}/receive`),
      x => x.crossdock_order ? `${a.number} → cross-dock ${x.crossdock_order} (no putaway)` : `${a.number} received${x.document ? ' → ' + x.document : ''}${x.crossdocked_qty ? ` · ${fmt(x.crossdocked_qty)} cross-docked` : ''}`)
    if (r) { reload(); if (r.document_id) nav(`/documents?open=${r.document_id}`) }
  }
  const create = async () => {
    if (await run(() => api.post(`/warehouses/${whId}/asns`, { vendor: f.vendor, eta: f.eta || null, lines }), 'ASN created')) { setLines([]); reload() }
  }
  return (
    <>
      <Card title="Advance shipping notices" sub="Expected receipts. Receiving creates putaway tasks; transfer ASNs at a hub are cross-docked instead.">
        <Table rows={asns} empty="No ASNs" cols={[
          { h: 'ASN', r: a => <b className="mono">{a.number}</b> }, { h: 'Vendor', r: a => a.vendor }, { h: 'ETA', mono: true, r: a => a.eta },
          { h: 'Lines', r: a => <span className="mono" style={{ fontSize: 12 }}>{a.lines.map(l => `${code(l.material_id)} × ${fmt(l.qty)}${l.tracking_no ? ' · ' + l.tracking_no : ''}`).join(', ')}</span> },
          { h: 'Type', r: a => a.hub_crossdock ? <span className="pill p-v">Hub cross-dock</span> : a.transfer_id ? <span className="pill p-b">Transfer</span> : '' },
          { h: 'Status', r: a => <Status s={a.status} /> },
          { h: '', r: a => a.status === 'OPEN' && can('release') && <button className="btn sm p" onClick={() => receive(a)}>Receive</button> },
        ]} />
      </Card>
      {can('create') && <Card title="New ASN">
        <div className="row"><Field label="Vendor"><input value={f.vendor} onChange={e => setF({ ...f, vendor: e.target.value })} /></Field>
          <Field label="ETA" w={160}><input type="date" value={f.eta} onChange={e => setF({ ...f, eta: e.target.value })} /></Field></div>
        <div style={{ marginTop: 9 }}><LineEditor mats={mats} lines={lines} setLines={setLines} /></div>
        <button className="btn p" style={{ marginTop: 10 }} disabled={!lines.length} onClick={create}>Create ASN</button>
      </Card>}
    </>
  )
}
