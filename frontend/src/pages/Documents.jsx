import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Note, Pill, Status, Table, fmt, useLoad } from '../ui.jsx'

const TITLE = { PUTAWAY: 'Putaway list', PICK: 'Pick list', REPLEN: 'Replenishment list', REARR: 'Rearrangement list', XDOCK: 'Cross-dock list' }

function Detail({ id, onChanged }) {
  const { whId, can, run } = useApp()
  const [d, reload] = useLoad(() => api.get(`/warehouses/${whId}/documents/${id}`), [id])
  const [sel, setSel] = useState(new Set())
  if (!d) return null
  const open = d.tasks.filter(t => t.status === 'OPEN')
  const confirm = async ids => { if (await run(() => api.post(`/warehouses/${whId}/tasks/confirm`, { ids }), x => `${x.confirmed} tasks confirmed`)) { setSel(new Set()); reload(); onChanged() } }
  return (
    <Card title={`${d.number} — ${TITLE[d.type]}`} sub={`${d.source} · ${d.steps}-step · ${d.strategy}${d.stage_bin ? ' · stage ' + d.stage_bin : ''}`}
      actions={can('confirm') && open.length > 0 && <>
        <button className="btn" disabled={!sel.size} onClick={() => confirm([...sel])}>Confirm selected ({sel.size})</button>
        <button className="btn p" onClick={() => confirm(open.map(t => t.id))}>Confirm all ({open.length})</button></>}>
      <Table rows={d.tasks} cols={[
        { h: '', r: t => t.status === 'OPEN' && <input type="checkbox" checked={sel.has(t.id)} onChange={e => { const s = new Set(sel); e.target.checked ? s.add(t.id) : s.delete(t.id); setSel(s) }} /> },
        { h: 'WT', mono: true, r: t => String(t.wt_number).padStart(6, '0') }, { h: 'WO', mono: true, r: t => t.wo_number || '—' },
        { h: 'Material', r: t => <>{t.level ? <span className="faint">{'↳ '.repeat(t.level)}</span> : null}<b className="mono">{t.material_code}</b><div className="sub">{t.material_name}{t.level ? ' · BOM component' : ''}</div></> },
        { h: 'Batch / serial', mono: true, r: t => t.tracking_no || '—' },
        { h: 'From → to', mono: true, r: t => `${t.source_bin || '—'} → ${t.dest_bin || '—'}` },
        { h: 'Orders', r: t => <span className="sub">{t.orders_ref}</span> }, { h: 'Qty', num: true, r: t => fmt(t.qty) },
        { h: 'Status', r: t => <Status s={t.status} /> },
      ]} />
      {d.shortages.length > 0 && <Note tone="danger"><b style={{ color: 'var(--danger)' }}>{d.type === 'PUTAWAY' ? 'No storage bin found' : 'Shortage'}</b> — {d.shortages.map(s => `${s.material_code} × ${fmt(s.qty)}`).join(', ')}</Note>}
    </Card>
  )
}

export default function Documents() {
  const { whId } = useApp()
  const [params, setParams] = useSearchParams()
  const [docs, reload] = useLoad(() => api.get(`/warehouses/${whId}/documents`), [whId])
  const [openId, setOpenId] = useState(Number(params.get('open')) || null)
  useEffect(() => { if (params.get('open')) setParams({}, { replace: true }) }, [])
  return (
    <>
      <Card title="Warehouse documents" sub="Putaway · pick · cross-dock lists. Each line is a warehouse task (WT).">
        <Table rows={docs} empty="No documents yet" cols={[
          { h: 'No.', r: d => <b className="mono">{d.number}</b> }, { h: 'Type', r: d => <Status s={d.type} /> },
          { h: 'Source', r: d => <span className="sub">{d.source}</span> }, { h: 'Strategy', mono: true, r: d => d.strategy },
          { h: 'Created', mono: true, r: d => d.created_at?.slice(0, 16).replace('T', ' ') },
          { h: 'Tasks', num: true, r: d => <>{d.done}/{d.tasks}{d.shortages ? <Pill tone="r">{d.shortages} short</Pill> : null}</> },
          { h: 'Status', r: d => <Status s={d.status} /> },
          { h: '', r: d => <button className="btn sm" onClick={() => setOpenId(d.id)}>Open</button> },
        ]} />
      </Card>
      {openId && <Detail key={openId} id={openId} onChanged={reload} />}
    </>
  )
}
