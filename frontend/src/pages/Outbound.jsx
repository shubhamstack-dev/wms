import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Field, Status, Table, fmt, useLoad } from '../ui.jsx'
import { LineEditor } from './Inbound.jsx'

export default function Outbound() {
  const { whId, can, run } = useApp()
  const nav = useNavigate()
  const [orders, reload] = useLoad(() => api.get(`/warehouses/${whId}/orders`), [whId])
  const [mats] = useLoad(() => api.get(`/materials?wh=${whId}`), [whId])
  const [sel, setSel] = useState(new Set())
  const [f, setF] = useState({ customer: '' })
  const [lines, setLines] = useState([])
  const code = id => mats?.find(m => m.id === id)?.code
  const open = (orders || []).filter(o => o.status === 'OPEN')
  const wave = async () => {
    const r = await run(() => api.post(`/warehouses/${whId}/waves`, { order_ids: [...sel] }), x => `${x.document} released`)
    if (r) { setSel(new Set()); nav(`/documents?open=${r.document_id}`) }
  }
  const create = async () => {
    if (await run(() => api.post(`/warehouses/${whId}/orders`, { customer: f.customer, lines: lines.map(l => ({ material_id: l.material_id, qty: l.qty })) }), 'Order created')) { setLines([]); reload() }
  }
  return (
    <>
      <Card title="Sales orders" sub="Select open orders and release them as one wave — tasks are bundled into warehouse orders for resources"
        actions={can('release') && <button className="btn p" disabled={!sel.size} onClick={wave}>Create wave ({sel.size})</button>}>
        <Table rows={orders} empty="No orders" cols={[
          { h: <input type="checkbox" checked={open.length > 0 && open.every(o => sel.has(o.id))} onChange={e => setSel(new Set(e.target.checked ? open.map(o => o.id) : []))} />,
            r: o => o.status === 'OPEN' && <input type="checkbox" checked={sel.has(o.id)} onChange={e => { const s = new Set(sel); e.target.checked ? s.add(o.id) : s.delete(o.id); setSel(s) }} /> },
          { h: 'Order', r: o => <b className="mono">{o.number}</b> }, { h: 'Customer', r: o => o.customer }, { h: 'Date', mono: true, r: o => o.order_date },
          { h: 'Lines', r: o => <span className="mono" style={{ fontSize: 12 }}>{o.lines.map(l => `${code(l.material_id)} × ${fmt(l.qty)}`).join(', ')}</span> },
          { h: 'Status', r: o => <Status s={o.status} /> }, { h: 'Wave', mono: true, r: o => o.wave_number || '—' },
        ]} />
      </Card>
      {can('create') && <Card title="New order">
        <div className="row"><Field label="Customer"><input value={f.customer} onChange={e => setF({ customer: e.target.value })} /></Field></div>
        <div style={{ marginTop: 9 }}><LineEditor mats={mats} lines={lines} setLines={setLines} tracking={false} /></div>
        <button className="btn p" style={{ marginTop: 10 }} disabled={!lines.length} onClick={create}>Create order</button>
      </Card>}
    </>
  )
}
