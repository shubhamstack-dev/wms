import React, { useState } from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, CrudCard, Field, Note, fmt, opts, useLoad } from '../ui.jsx'

function BomEditor({ mats }) {
  const { can, run } = useApp()
  const [boms, reload] = useLoad(() => api.get('/boms'), [])
  const [parent, setParent] = useState('')
  const [comps, setComps] = useState([])
  const [add, setAdd] = useState({ material_id: '', qty: 1 })
  const code = id => mats?.find(m => m.id === id)?.code || '?'
  const pick = id => { setParent(id); setComps((boms || []).find(b => b.parent_material_id === Number(id))?.components || []) }
  const save = async () => { if (await run(() => api.put(`/boms/${parent}`, { components: comps }), 'BOM saved')) reload() }
  return (
    <Card title="Bills of material" sub="When the parent is short at picking, components are picked instead (multi-level, see Strategies)">
      {(boms || []).map(b => <div key={b.parent_material_id} style={{ marginBottom: 6 }}><b className="mono">{code(b.parent_material_id)}</b>
        <span className="dim"> ← {b.components.map(c => `${code(c.material_id)} × ${fmt(c.qty)}`).join(', ')}</span></div>)}
      {can('master') && <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
        <div className="row"><Field label="Parent material"><select value={parent} onChange={e => pick(e.target.value)}>
          <option value="">— choose —</option>{opts(mats).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field></div>
        {parent && <>
          <div style={{ margin: '9px 0' }}>{comps.length ? comps.map((c, i) => <span key={i} className="pill p-b">{code(c.material_id)} × {fmt(c.qty)}
            <a href="#" style={{ color: 'inherit', marginLeft: 4 }} onClick={e => { e.preventDefault(); setComps(comps.filter((_, j) => j !== i)) }}>✕</a></span>)
            : <span className="faint">No components — saving removes the BOM</span>}</div>
          <div className="row"><Field label="Component"><select value={add.material_id} onChange={e => setAdd(a => ({ ...a, material_id: Number(e.target.value) }))}>
            <option value="">—</option>{opts((mats || []).filter(m => m.id !== Number(parent))).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Qty" w={90}><input type="number" value={add.qty} onChange={e => setAdd(a => ({ ...a, qty: Number(e.target.value) }))} /></Field>
            <button className="btn" disabled={!add.material_id || !(add.qty > 0)} onClick={() => setComps([...comps, add])}>Add</button>
            <button className="btn p" onClick={save}>Save BOM</button></div></>}
      </div>}
    </Card>
  )
}

export default function Materials() {
  const { whId } = useApp()
  const [mats, reload] = useLoad(() => api.get(`/materials${whId ? `?wh=${whId}` : ''}`), [whId])
  return (
    <>
      <CrudCard title="Material master" sub="One global material master shared by all warehouses. Tracking decides whether a batch or serial is required."
        path="/materials" sing="material" onChanged={reload}
        fields={[{ k: 'code', l: 'Code', t: 'code' }, { k: 'name', l: 'Description' }, { k: 'uom', l: 'UoM', d: 'EA' },
          { k: 'type', l: 'Type', t: 'sel', o: () => [['FG', 'FG'], ['SFG', 'SFG'], ['RM', 'RM'], ['PACK', 'PACK']], d: 'FG' },
          { k: 'tracking', l: 'Tracking', t: 'sel', o: () => [['NONE', 'None'], ['BATCH', 'Batch'], ['SERIAL', 'Serial']], d: 'NONE' },
          { k: 'weight', l: 'kg / unit', t: 'num' }, { k: 'volume', l: 'm³ / unit', t: 'num' }]}
        extra={[['Stock (this WH)', r => fmt(mats?.find(m => m.id === r.id)?.stock || 0)]]} />
      <BomEditor mats={mats} />
      <Note>Material code cannot be changed after creation — other systems reference it.</Note>
    </>
  )
}
