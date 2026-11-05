import React, { useState } from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { checkGstin } from '../gstin.js'
import { Card, CrudCard, Drawer, Field, Note, Pill, SubNav, Table, fmt, opts, useLoad } from '../ui.jsx'

const TYPES = [['DC', 'Distribution centre'], ['PLANT', 'Plant warehouse'], ['XD', 'Cross-dock hub']]
const ADDR = ['addr_line1', 'addr_line2', 'city', 'district', 'state_code', 'pin', 'country']

function addressLines(w, states) {
  return [w.addr_line1, w.addr_line2, [w.city, w.district].filter(Boolean).join(', '),
    [states[w.state_code] && `${states[w.state_code]} (${w.state_code})`, w.pin].filter(Boolean).join(' — '), w.country].filter(Boolean)
}

function AddrBlock({ w, states }) {
  const ls = addressLines(w, states)
  return (
    <div className="addrbox">
      <div>{ls.length ? ls.map((l, i) => <div key={i}>{l}</div>) : <span className="faint">Address not maintained</span>}</div>
      <div style={{ marginTop: 6 }}><b className="mono">GSTIN {w.gstin || '—'}</b>{' '}
        <Pill tone={w.gstin_valid ? 'g' : 'r'}>{w.gstin_valid ? 'Valid' : w.gstin ? 'Invalid' : 'Missing'}</Pill></div>
      {w.issues?.length ? <div style={{ color: 'var(--warn)', fontSize: 11.5, marginTop: 4 }}>{w.issues.join(' · ')}</div>
        : <div style={{ color: 'var(--ok)', fontSize: 11.5, marginTop: 4 }}>Complete — ready to pass to other systems</div>}
    </div>
  )
}

function WarehouseForm({ w, onDone }) {
  const { meta, whs, run } = useApp()
  const states = meta.gst_states || {}
  const [plants] = useLoad(() => api.get('/plants'), [])
  const [f, setF] = useState(() => w ? { ...w } : { code: '', name: '', type: 'DC', country: 'India', copy_bins: false, sloc_code: '' })
  const set = (k, v) => setF(x => ({ ...x, [k]: v }))
  const g = checkGstin(f.gstin, states)
  const stateMismatch = g.ok && f.state_code && f.state_code !== g.state
  const save = async () => {
    const body = { code: f.code, name: f.name, type: f.type, trade_name: f.trade_name || '', gstin: f.gstin || '', contact: f.contact || '',
      phone: f.phone || '', email: f.email || '', ...Object.fromEntries(ADDR.map(k => [k, f[k] || (k === 'country' ? 'India' : '')])) }
    if (!w) Object.assign(body, { copy_from_id: f.copy_from_id || null, copy_bins: !!f.copy_bins, plant_id: f.plant_id || null, sloc_code: f.sloc_code || '' })
    const r = await run(() => (w ? api.put(`/warehouses/${w.id}`, body) : api.post('/warehouses', body)), w ? 'Saved' : 'Warehouse created')
    if (r) onDone(r)
  }
  const T = (k, l, extra = {}) => <Field label={l}><input value={f[k] || ''} onChange={e => set(k, e.target.value)} {...extra} /></Field>
  return (
    <>
      <div className="row">{T('code', 'Warehouse no.', { style: { textTransform: 'uppercase' }, placeholder: 'WH03' })}{T('name', 'Name')}</div>
      <div className="row" style={{ marginTop: 9 }}>
        <Field label="Type"><select value={f.type} onChange={e => set('type', e.target.value)}>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        {T('trade_name', 'Trade name (optional)')}</div>
      <h3 style={{ fontSize: 13, margin: '16px 0 8px' }}>Address</h3>
      {T('addr_line1', 'Address line 1')}
      <div style={{ marginTop: 8 }}>{T('addr_line2', 'Address line 2')}</div>
      <div className="row" style={{ marginTop: 8 }}>{T('city', 'City')}{T('district', 'District')}</div>
      <div className="row" style={{ marginTop: 8 }}>
        <Field label="State"><select value={f.state_code || ''} onChange={e => set('state_code', e.target.value)}>
          <option value="">— choose —</option>{Object.entries(states).map(([c, n]) => <option key={c} value={c}>{c} — {n}</option>)}</select></Field>
        <Field label="PIN code" w={110}><input value={f.pin || ''} maxLength={6} inputMode="numeric" onChange={e => set('pin', e.target.value)} /></Field></div>
      <h3 style={{ fontSize: 13, margin: '16px 0 8px' }}>GST registration</h3>
      <label>GSTIN</label>
      <input className="mono" maxLength={15} value={f.gstin || ''} style={{ textTransform: 'uppercase' }}
        onChange={e => set('gstin', e.target.value.toUpperCase())}
        onBlur={() => { if (g.ok && !f.state_code) set('state_code', g.state) }} placeholder="29AABCB1234F1Z5" />
      <Note tone={g.empty ? null : !g.ok ? 'danger' : stateMismatch ? 'warn' : 'ok'}>
        {g.empty ? 'Optional — captured only to pass to connected systems (ERP, e-way bill, transport). No billing here.'
          : !g.ok ? <><b style={{ color: 'var(--danger)' }}>Invalid</b> — {g.msg}</>
            : <><b style={{ color: 'var(--ok)' }}>Valid GSTIN</b> — state {g.state} {states[g.state]} · PAN {g.pan}
              {stateMismatch && <><br /><b style={{ color: 'var(--warn)' }}>GSTIN is for {states[g.state]} but the address state is {states[f.state_code]}</b></>}</>}
      </Note>
      <h3 style={{ fontSize: 13, margin: '16px 0 8px' }}>Contact</h3>
      <div className="row">{T('contact', 'Contact person')}{T('phone', 'Phone')}</div>
      <div style={{ marginTop: 8 }}>{T('email', 'Email', { type: 'email' })}</div>
      {!w && <>
        <h3 style={{ fontSize: 13, margin: '16px 0 8px' }}>Organisation</h3>
        <div className="row">
          <Field label="Plant"><select value={f.plant_id || ''} onChange={e => set('plant_id', Number(e.target.value) || null)}>
            <option value="">— assign later —</option>{opts(plants).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Storage location" w={120}><input value={f.sloc_code} placeholder="0003" onChange={e => set('sloc_code', e.target.value)} /></Field></div>
        <div style={{ marginTop: 9 }}><Field label="Start from"><select value={f.copy_from_id || ''} onChange={e => set('copy_from_id', Number(e.target.value) || null)}>
          <option value="">Empty warehouse</option>{whs.map(x => <option key={x.id} value={x.id}>Copy structure of {x.code}</option>)}</select></Field></div>
        <label className="ck" style={{ marginTop: 9 }}><input type="checkbox" checked={f.copy_bins} disabled={!f.copy_from_id}
          onChange={e => set('copy_bins', e.target.checked)} /> Also copy bins &amp; racks (empty, no stock)</label>
      </>}
      <div className="row" style={{ marginTop: 14 }}><button className="btn p" onClick={save} disabled={!g.ok && !g.empty}>{w ? 'Save' : 'Create warehouse'}</button></div>
    </>
  )
}

function Warehouses() {
  const { whs, whId, setWhId, refreshWhs, can, run, meta } = useApp()
  const [form, setForm] = useState(null)
  const del = async w => {
    if (!confirm(`Delete warehouse ${w.code}?`)) return
    if (await run(() => api.del(`/warehouses/${w.id}`), `${w.code} deleted`)) refreshWhs()
  }
  return (
    <Card title="Warehouse numbers" sub="Each warehouse has its own organisation, bins, stock and execution. Switch with the selector in the header."
      actions={can('setup') && <button className="btn p" onClick={() => setForm({})}>New warehouse</button>}>
      <div className="whgrid">{whs.map(w => {
        const act = w.id === whId
        return (
          <div key={w.id} className={'whcard' + (act ? ' act' : '')}>
            <div className="row nowrap"><b className="mono" style={{ fontSize: 15 }}>{w.code}</b>
              <Pill tone={w.type === 'XD' ? 'v' : w.type === 'PLANT' ? 'y' : 'b'}>{TYPES.find(t => t[0] === w.type)?.[1]}</Pill>
              {act && <Pill tone="g">Active</Pill>}</div>
            <div style={{ marginTop: 3 }}>{w.name}</div>
            <div className="sub">{w.city || '—'} · Plant/SLoc {w.storage_locations.join(', ') || 'not assigned'}</div>
            <div style={{ fontSize: 12, marginTop: 3 }}><span className="mono">GSTIN {w.gstin || '—'}</span>{' '}
              {w.gstin_valid && !w.issues.length ? <Pill tone="g">GST data ✓</Pill> : <Pill tone="y" title={w.issues.join(' · ')}>{w.issues.length} issue{w.issues.length === 1 ? '' : 's'}</Pill>}</div>
            <div className="whk">{[[w.bins, 'bins'], [w.storage_types, 'storage types'], [fmt(w.units), 'units'], [w.open_docs, 'open docs'],
              [w.open_asns, 'open ASNs'], [w.open_xd, 'XD orders'], [w.inbound_transfers, 'inbound transfers'], [w.outbound_transfers, 'to ship']]
              .map(([v, l]) => <div key={l}><b>{v}</b><span>{l}</span></div>)}</div>
            <div className="row" style={{ marginTop: 10, gap: 6 }}>
              {!act && <button className="btn sm p" onClick={() => setWhId(w.id)}>Open</button>}
              {can('setup') && <button className="btn sm" onClick={() => setForm({ w })}>Edit</button>}
              {can('setup') && !act && whs.length > 1 && <button className="btn sm d" onClick={() => del(w)}>Delete</button>}</div>
          </div>)
      })}</div>
      <Drawer open={!!form} title={form?.w ? `Warehouse ${form.w.code}` : 'New warehouse'} onClose={() => setForm(null)}>
        {form && <WarehouseForm w={form.w} onDone={async r => { setForm(null); await refreshWhs(); if (!form.w) setWhId(r.id) }} />}
      </Drawer>
    </Card>
  )
}

function GstData() {
  const { whs, meta, run } = useApp()
  const states = meta.gst_states || {}
  const bad = whs.filter(w => w.issues.length).length
  return (
    <>
      <Card title="Address & GST master data" sub="Captured only to pass to other systems (ERP, e-way bill, transport, finance). No billing happens here.">
        <div className="whgrid">{whs.map(w => (
          <div key={w.id} className="whcard"><div className="row nowrap"><b className="mono">{w.code}</b> {w.name}</div><AddrBlock w={w} states={states} /></div>
        ))}</div>
      </Card>
      <Card title="Export for other systems" sub={bad ? `${bad} warehouse(s) have incomplete data — exported with an "issues" field.` : 'All warehouses are complete.'}>
        <div className="row">
          <button className="btn p" onClick={() => run(() => api.download('/exports/gst-master.json', 'warehouse-gst-master.json'))}>Warehouse GST master (JSON)</button>
          <button className="btn" onClick={() => run(() => api.download('/exports/gst-master.csv', 'warehouse-gst-master.csv'))}>Warehouse GST master (CSV)</button>
          <button className="btn" onClick={() => run(() => api.download('/exports/transfers.json', 'stock-transfers-gst.json'))}>Stock transfers with GSTINs (JSON)</button>
        </div>
        <Note>The API serves the same data for direct integration: <span className="mono">GET /api/exports/gst-master.json</span>,{' '}
          <span className="mono">/api/exports/gst-master.csv</span>, <span className="mono">/api/exports/transfers.json</span>.</Note>
      </Card>
    </>
  )
}

function Units() {
  const { whs, refreshWhs } = useApp()
  const [companies, reloadC] = useLoad(() => api.get('/companies'), [])
  const [plants, reloadP] = useLoad(() => api.get('/plants'), [])
  return (
    <>
      <CrudCard title="Company codes" sub="Legal entity — top of the enterprise structure" path="/companies" sing="company code" onChanged={reloadC}
        fields={[{ k: 'code', l: 'Code', t: 'code' }, { k: 'name', l: 'Name' }, { k: 'legal_name', l: 'Registered legal name' },
          { k: 'pan', l: 'PAN', t: 'code' }, { k: 'cin', l: 'CIN', t: 'code' }, { k: 'currency', l: 'Currency', t: 'code', d: 'INR' }]} />
      <CrudCard title="Plants" sub="Production / distribution site within a company code" path="/plants" sing="plant" onChanged={reloadP}
        fields={[{ k: 'code', l: 'Code', t: 'code' }, { k: 'name', l: 'Name' },
          { k: 'company_id', l: 'Company code', t: 'sel', num: true, o: () => opts(companies) }, { k: 'city', l: 'City' }]} />
      <CrudCard title="Storage locations" sub="Plant + storage location → warehouse number: decides which warehouse manages the inventory"
        path="/storage-locations" sing="storage location" onChanged={refreshWhs}
        fields={[{ k: 'plant_id', l: 'Plant', t: 'sel', num: true, o: () => opts(plants) }, { k: 'code', l: 'Code', t: 'code' },
          { k: 'name', l: 'Name' }, { k: 'warehouse_id', l: 'Warehouse number', t: 'sel', num: true, o: () => opts(whs) }]} />
    </>
  )
}

function Tree() {
  const { whs, setWhId } = useApp()
  const [c] = useLoad(() => api.get('/companies'), [])
  const [p] = useLoad(() => api.get('/plants'), [])
  const [s] = useLoad(() => api.get('/storage-locations'), [])
  const chip = id => { const w = whs.find(x => x.id === id)
    return w ? <button className="leaf" onClick={() => setWhId(w.id)}><b className="mono">{w.code}</b> {w.name}</button> : <span className="faint">not warehouse-managed</span> }
  return (
    <Card title="Enterprise structure" sub="Company code → plant → storage location → warehouse number. Click a warehouse to switch to it.">
      <div className="otree">{(c || []).map(co => (
        <div key={co.id} style={{ marginBottom: 14 }}>
          <div className="onode root"><b className="mono">{co.code}</b> {co.legal_name || co.name}<span className="om">{co.currency} · PAN {co.pan || '—'}</span></div>
          <div className="ochildren">{(p || []).filter(x => x.company_id === co.id).map(pl => (
            <div key={pl.id}><div className="onode"><Pill tone="y">Plant</Pill><b className="mono">{pl.code}</b> {pl.name}<span className="om">{pl.city}</span></div>
              <div className="ochildren">{(s || []).filter(x => x.plant_id === pl.id).map(sl => (
                <div key={sl.id} className="row nowrap"><Pill>SLoc {sl.code}</Pill><span style={{ fontSize: 12.5 }}>{sl.name}</span><span className="faint">→</span>{chip(sl.warehouse_id)}</div>
              ))}</div></div>
          ))}</div>
        </div>))}</div>
    </Card>
  )
}

function StockOverview() {
  const { whs } = useApp()
  const [rows] = useLoad(() => api.get('/stock-overview'), [])
  return (
    <Card title="Stock across warehouses" sub="Material availability per warehouse number, plus goods on the road between warehouses">
      <Table rows={rows} rowKey={r => r.material_id} cols={[
        { h: 'Material', r: r => <><b className="mono">{r.code}</b><div className="sub">{r.name}</div></> },
        ...whs.map(w => ({ h: w.code, num: true, r: r => r.by_warehouse[w.id] ? fmt(r.by_warehouse[w.id]) : <span className="faint">—</span> })),
        { h: 'In transit', num: true, r: r => r.in_transit ? <span style={{ color: 'var(--accent)' }}>{fmt(r.in_transit)}</span> : <span className="faint">—</span> },
        { h: 'Total', num: true, r: r => <b>{fmt(Object.values(r.by_warehouse).reduce((a, b) => a + b, 0) + r.in_transit)}</b> },
      ]} />
    </Card>
  )
}

function Migration() {
  const { can, run, refreshWhs } = useApp()
  const [file, setFile] = useState(null)
  const [replace, setReplace] = useState(false)
  const [res, setRes] = useState(null)
  const go = async () => {
    let data
    try { data = JSON.parse(await file.text()) } catch { return alert('This is not a JSON export from the HTML app') }
    if (replace && !confirm('This deletes everything in the database first. Continue?')) return
    const r = await run(() => api.post(`/admin/import-legacy?replace=${replace}`, data), x => `Imported ${x.imported.warehouses} warehouses`)
    if (r) { setRes(r); refreshWhs() }
  }
  return (
    <Card title="Migrate from the single-file HTML app" sub="In the old app press Export (header) and upload the wms-data-….json file here">
      {!can('reset') ? <Note tone="warn">Only the Admin role can import data.</Note> : <>
        <div className="row"><Field label="Export file"><input type="file" accept=".json,application/json" onChange={e => setFile(e.target.files[0] || null)} /></Field></div>
        <label className="ck" style={{ marginTop: 9 }}><input type="checkbox" checked={replace} onChange={e => setReplace(e.target.checked)} /> Replace all existing data (needed if the database is not empty)</label>
        <button className="btn p" style={{ marginTop: 10 }} disabled={!file} onClick={go}>Import</button>
        <Note>Imported: enterprise structure, warehouses with address &amp; GSTIN, storage types, sections, bin types, activity areas, queues,
          resources, doors, racks, bins, materials, BOMs, stock (batch / serial / expiry), open ASNs and open orders. History stays in the file.</Note>
        {res && <Note tone={res.warnings.length ? 'warn' : 'ok'}>{Object.entries(res.imported).map(([k, v]) => `${v} ${k}`).join(' · ')}
          {res.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}</Note>}
      </>}
    </Card>
  )
}

export default function Enterprise() {
  const [tab, setTab] = useState('wh')
  return (
    <>
      <SubNav value={tab} onChange={setTab} tabs={[['wh', 'Warehouses'], ['gst', 'Address & GST'], ['tree', 'Enterprise structure'],
        ['units', 'Company, plant & storage location'], ['stock', 'Stock across warehouses'], ['mig', 'Migration']]} />
      {tab === 'wh' && <Warehouses />}{tab === 'gst' && <GstData />}{tab === 'tree' && <Tree />}
      {tab === 'units' && <Units />}{tab === 'stock' && <StockOverview />}{tab === 'mig' && <Migration />}
    </>
  )
}
