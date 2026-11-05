import React from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Field, Note, useLoad } from '../ui.jsx'

export default function Strategies() {
  const { whId, can, run } = useApp()
  const [cfg, reload] = useLoad(() => api.get(`/warehouses/${whId}/config`), [whId])
  const [bins] = useLoad(() => api.get(`/warehouses/${whId}/bins`), [whId])
  if (!cfg) return <Card><div className="empty">Loading…</div></Card>
  const ro = !can('config')
  const set = async patch => { if (await run(() => api.put(`/warehouses/${whId}/config`, patch), 'Saved')) reload() }
  const S = (k, options, numeric) => (
    <select disabled={ro} value={cfg[k] ?? ''} onChange={e => set({ [k]: numeric ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value })}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>)
  const lanes = [['', '— none —'], ...(bins || []).filter(b => b.role !== 'STORAGE').map(b => [b.id, `${b.code} (${b.role.toLowerCase()})`])]
  return (
    <>
      {ro && <Note tone="warn">Read-only — configuration needs the Admin role.</Note>}
      <div className="grid g2" style={{ marginTop: 10 }}>
        <Card title="Putaway" sub="Where incoming goods are stored">
          <Field label="Process steps">{S('putaway_steps', [[1, '1-step — straight to the final bin'], [2, '2-step — receiving bin, then putaway']], true)}</Field>
          <div style={{ marginTop: 10 }}><Field label="Bin selection">{S('putaway_strategy', [['nearest', 'Nearest — storage type rank, then distance'],
            ['fixed', 'Fixed bin first'], ['consolidate', 'Consolidate — where the material already is'], ['capacity', 'Max capacity — emptiest bin']])}</Field></div>
          <div style={{ marginTop: 10 }}><Field label="Receiving bin (2-step)">{S('stage_in_bin_id', lanes, true)}</Field></div>
          <Note>A bin fixed to a material is always preferred. Storage types with mixed storage switched off never receive a second material.</Note>
        </Card>
        <Card title="Picking" sub="Which stock leaves first">
          <Field label="Process steps">{S('pick_steps', [[1, '1-step — bin straight to goods issue'], [2, '2-step — staging bin, then ship']], true)}</Field>
          <div style={{ marginTop: 10 }}><Field label="Pick strategy">{S('pick_strategy', [['FEFO', 'FEFO — first expiry first'], ['FIFO', 'FIFO — first in first out'],
            ['LIFO', 'LIFO — last in first out'], ['nearest', 'Shortest path'], ['fixed', 'Fixed bin first']])}</Field></div>
          <div style={{ marginTop: 10 }}><Field label="Staging bin (2-step)">{S('stage_out_bin_id', lanes, true)}</Field></div>
          <div style={{ marginTop: 10 }}><Field label="BOM handling"><select disabled={ro} value={String(cfg.explode_bom)} onChange={e => set({ explode_bom: e.target.value === 'true' })}><option value="true">Explode — pick components if the parent is short</option><option value="false">Off</option></select></Field></div>
        </Card>
        <Card title="Cross-docking" sub="Bins used for flow-through">
          <Field label="Inbound cross-dock bin">{S('xd_in_bin_id', lanes, true)}</Field>
          <div style={{ marginTop: 10 }}><Field label="Outbound cross-dock bin">{S('xd_out_bin_id', lanes, true)}</Field></div>
          <div style={{ marginTop: 10 }}><Field label="Opportunistic cross-docking">
            <select disabled={ro} value={String(cfg.xdock_opportunistic)} onChange={e => set({ xdock_opportunistic: e.target.value === 'true' })}>
              <option value="true">On — receipts fill pick shortages first</option><option value="false">Off</option></select></Field></div>
        </Card>
        <Card title="Warehouse orders" sub="How tasks are bundled for resources">
          <Field label="Max tasks per warehouse order"><input type="number" min={1} disabled={ro} defaultValue={cfg.wo_max_tasks}
            onBlur={e => Number(e.target.value) !== cfg.wo_max_tasks && set({ wo_max_tasks: Math.max(1, Number(e.target.value) || 6) })} /></Field>
          <Note>Tasks are grouped per activity area, sorted along the path (serpentine or aisle by aisle), then split at this size.</Note>
        </Card>
      </div>
    </>
  )
}
