import React, { useState } from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Field, Table, fmt, useLoad } from '../ui.jsx'

export default function Stock() {
  const { whId } = useApp()
  const [rows] = useLoad(() => api.get(`/warehouses/${whId}/stock`), [whId])
  const [q, setQ] = useState('')
  const f = (rows || []).filter(r => !q || `${r.bin_code} ${r.material_code} ${r.batch} ${r.serial}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <Card title="Stock by bin" sub={`${f.length} quants · ${fmt(f.reduce((a, r) => a + r.qty, 0))} units`}>
      <div className="row" style={{ marginBottom: 10 }}><Field label="Search bin, material, batch or serial"><input value={q} onChange={e => setQ(e.target.value)} /></Field></div>
      <Table rows={f} empty="No stock" cols={[
        { h: 'Bin', r: r => <b className="mono">{r.bin_code}</b> }, { h: 'Material', r: r => <><b className="mono">{r.material_code}</b> <span className="dim">{r.material_name}</span></> },
        { h: 'Batch / serial', mono: true, r: r => r.batch || r.serial || '—' }, { h: 'Expiry', mono: true, r: r => r.expiry || '—' },
        { h: 'Qty', num: true, r: r => `${fmt(r.qty)} ${r.uom}` },
      ]} />
    </Card>
  )
}
