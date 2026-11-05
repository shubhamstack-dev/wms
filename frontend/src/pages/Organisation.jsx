import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, CrudCard, Pill, SubNav, Table, opts, useLoad } from '../ui.jsx'

const ROLE_OPTS = [['STORAGE', 'Storage'], ['RECEIVING', 'Receiving (GR)'], ['QC', 'Quality inspection'], ['STAGING', 'Staging'], ['SHIPPING', 'Shipping (GI)']]
const TASKS = [['PICK', 'Picking'], ['PUTAWAY', 'Putaway'], ['REPLEN', 'Replenishment'], ['REARR', 'Rearrangement'], ['XDOCK', 'Cross-dock']]

function useOrgData(whId) {
  const W = p => api.get(`/warehouses/${whId}/${p}`)
  const [st, rSt] = useLoad(() => W('storage-types'), [whId])
  const [sec, rSec] = useLoad(() => W('sections'), [whId])
  const [aa, rAa] = useLoad(() => W('activity-areas'), [whId])
  const [q, rQ] = useLoad(() => W('queues'), [whId])
  const [rt, rRt] = useLoad(() => W('resource-types'), [whId])
  const [bins, rBins] = useLoad(() => W('bins'), [whId])
  const [racks, rRacks] = useLoad(() => W('racks'), [whId])
  return { st, sec, aa, q, rt, bins, racks, reload: () => [rSt, rSec, rAa, rQ, rRt, rBins, rRacks].forEach(f => f()) }
}

function Structure({ d }) {
  const { wh } = useApp()
  const nav = useNavigate()
  const bins = d.bins || []
  const miss = [['Storage bins without section', bins.filter(b => b.role === 'STORAGE' && !b.section_id).length, 'nosec'],
    ['Bins without bin type', bins.filter(b => !b.bin_type_id).length, 'nobt'], ['Bins without activity area', bins.filter(b => !b.activity_area_id).length, 'noaa']]
  return (
    <>
      <Card title="Physical structure" sub="Warehouse → storage type → section / rack → bins. Click to open the bins in the layout designer.">
        <div className="otree">
          <div className="onode root"><b className="mono">{wh?.code}</b> {wh?.name}<span className="om">{bins.length} bins</span></div>
          <div className="ochildren">{(d.st || []).map(t => {
            const tb = bins.filter(b => b.storage_type_id === t.id)
            return (
              <div key={t.id}>
                <div className="onode"><Pill tone={t.role === 'STORAGE' ? 'b' : 'm'}>{t.role}</Pill><b className="mono">{t.code}</b> {t.name}
                  <span className="om">{tb.length} bins{t.mixed_storage ? '' : ' · no mixing'}</span>
                  <button className="btn sm" onClick={() => nav(`/designer?focus=stype:${t.id}`)}>Show</button></div>
                <div className="oleaves">
                  {(d.sec || []).filter(s => s.storage_type_id === t.id).map(s => (
                    <button key={s.id} className="leaf" onClick={() => nav(`/designer?focus=section:${s.id}`)}>
                      <b className="mono">{s.code}</b> {s.name} <span className="dim">· {tb.filter(b => b.section_id === s.id).length}</span></button>))}
                  {(d.racks || []).filter(r => r.storage_type_id === t.id).map(r => (
                    <button key={'r' + r.id} className="leaf" style={{ borderColor: 'var(--accent)' }} onClick={() => nav(`/designer?rack=${r.id}`)}>
                      Rack <b className="mono">{r.code}</b> <span className="dim">· {r.generated} bins</span></button>))}
                  {t.role === 'STORAGE' && <button className="leaf" style={{ borderStyle: 'dashed', color: 'var(--accent)' }}
                    onClick={() => nav(`/designer?rack=new&st=${t.id}`)}>+ Rack</button>}
                </div>
              </div>)
          })}</div>
        </div>
      </Card>
      <Card title="Bin assignment check" sub="Prerequisites every bin should have">
        <div className="grid g3">{miss.map(([l, n, k]) => (
          <div key={k} className="kpi"><div className="v" style={{ color: n ? 'var(--warn)' : 'var(--ok)' }}>{n}</div><div className="l">{l}</div>
            {n ? <button className="btn sm" style={{ marginTop: 8 }} onClick={() => nav(`/designer?focus=${k}:all`)}>Assign in designer</button> : null}</div>))}</div>
      </Card>
    </>
  )
}

function Racks({ d }) {
  const { whId, can, run } = useApp()
  const nav = useNavigate()
  const act = async (fn, msg) => { if (await run(fn, msg)) d.reload() }
  return (
    <Card title="Racks / bin structures" sub="Each rack: start point → end point, aisles, positions and levels. Bins are generated from this definition."
      actions={can('setup') && <button className="btn sm p" onClick={() => nav('/designer?rack=new')}>New rack</button>}>
      <Table rows={d.racks} empty="No racks yet" cols={[
        { h: 'Rack', r: r => <><b className="mono">{r.code}</b><div className="sub">{r.name}</div></> },
        { h: 'Storage type', mono: true, r: r => d.st?.find(t => t.id === r.storage_type_id)?.code },
        { h: 'Start → end', mono: true, r: r => `(${r.x1},${r.y1}) → (${r.x2},${r.y2})` },
        { h: 'Aisles', num: true, r: r => `${r.aisle_from}–${r.aisle_to}` }, { h: 'Positions', num: true, r: r => r.positions },
        { h: 'Levels', num: true, r: r => `${r.level_from}–${r.level_to}` },
        { h: 'Code range', mono: true, r: r => <>{r.first_code}<br />{r.last_code}</> },
        { h: 'Bins', num: true, r: r => <><b>{r.generated}</b> / {r.planned}</> },
        { h: '', r: r => <span className="row nowrap">
          <button className="btn sm" onClick={() => nav(`/designer?rack=${r.id}`)}>Open</button>
          {can('setup') && <>
            <button className="btn sm p" disabled={!r.new} onClick={() => act(() => api.post(`/warehouses/${whId}/racks/${r.id}/generate`), x => `${x.made} bins generated`)}>Generate {r.new || ''}</button>
            <button className="btn sm d" disabled={!r.generated} onClick={() => confirm(`Delete all empty bins of ${r.code}?`) &&
              act(() => api.post(`/warehouses/${whId}/racks/${r.id}/delete-bins`), x => `${x.deleted} bins deleted`)}>Delete bins</button></>}
        </span> },
      ]} />
    </Card>
  )
}

export default function Organisation() {
  const { whId } = useApp()
  const [tab, setTab] = useState('tree')
  const d = useOrgData(whId)
  const P = p => `/warehouses/${whId}/${p}`
  const nonStorage = () => (d.bins || []).filter(b => b.role !== 'STORAGE').map(b => [b.id, b.code])
  const code = { k: 'code', l: 'Code', t: 'code' }, name = { k: 'name', l: 'Description' }
  return (
    <>
      <SubNav value={tab} onChange={setTab} tabs={[['tree', 'Structure'], ['phys', 'Storage types & sections'], ['bt', 'Bin types'],
        ['racks', 'Racks'], ['exec', 'Activity areas & queues'], ['res', 'Resources'], ['wc', 'Work centers & doors']]} />
      {tab === 'tree' && <Structure d={d} />}
      {tab === 'racks' && <Racks d={d} />}
      {tab === 'phys' && <>
        <CrudCard title="Storage types" sub="Physical/logical areas with a role and putaway / picking control" path={P('storage-types')} sing="storage type" onChanged={d.reload}
          fields={[code, name, { k: 'role', l: 'Role', t: 'sel', o: () => ROLE_OPTS, d: 'STORAGE' }, { k: 'putaway_rank', l: 'Putaway rank', t: 'num', d: 1 },
            { k: 'pick_rank', l: 'Pick rank', t: 'num', d: 1 }, { k: 'mixed_storage', l: 'Mixed storage allowed', t: 'bool', d: true }]} />
        <CrudCard title="Storage sections" sub="Groups inside a storage type — fast movers, heavy goods, upper levels…" path={P('sections')} sing="section" onChanged={d.reload}
          fields={[{ k: 'storage_type_id', l: 'Storage type', t: 'sel', num: true, o: () => opts(d.st) }, code, name]} />
      </>}
      {tab === 'bt' && <CrudCard title="Bin types" sub="Physical bin format — its capacity is applied to every bin of this type (0 = no limit)" path={P('bin-types')} sing="bin type" onChanged={d.reload}
        fields={[code, name, { k: 'max_qty', l: 'Max qty', t: 'num' }, { k: 'max_weight', l: 'Max kg', t: 'num' }, { k: 'max_volume', l: 'Max m³', t: 'num' }]} />}
      {tab === 'exec' && <>
        <CrudCard title="Activity areas" sub="Execution grouping of bins — warehouse orders are built and sequenced per area" path={P('activity-areas')} sing="activity area" onChanged={d.reload}
          fields={[code, name, { k: 'activity', l: 'Activity', t: 'sel', o: () => [['ALL', 'All'], ['PICK', 'Picking'], ['PTWY', 'Putaway'], ['INVE', 'Inventory']], d: 'ALL' },
            { k: 'path_sort', l: 'Path sequence', t: 'sel', o: () => [['serp', 'Serpentine (S-path)'], ['aisle', 'Aisle by aisle']], d: 'serp' }]} />
        <CrudCard title="Queues" sub="Activity area + task type → queue. Resources take work from their queues." path={P('queues')} sing="queue" onChanged={d.reload}
          fields={[code, name, { k: 'activity_area_ids', l: 'Activity areas (none = all)', t: 'multi', o: () => opts(d.aa, r => r.code) },
            { k: 'task_types', l: 'Task types', t: 'multi', o: () => TASKS }]} />
      </>}
      {tab === 'res' && <>
        <CrudCard title="Resource types" sub="Equipment / user group — max level decides which bins it can reach (0 = unlimited)" path={P('resource-types')} sing="resource type" onChanged={d.reload}
          fields={[code, name, { k: 'max_level', l: 'Max level (Z)', t: 'num' }]} />
        <CrudCard title="Resources" sub="Operators / equipment that execute warehouse orders" path={P('resources')} sing="resource" onChanged={d.reload}
          fields={[code, { k: 'name', l: 'Operator' }, { k: 'resource_type_id', l: 'Resource type', t: 'sel', num: true, o: () => opts(d.rt) },
            { k: 'queue_ids', l: 'Queues (none = all)', t: 'multi', o: () => opts(d.q, r => r.code) }]}
          extra={[['Status', r => <Pill tone={r.status === 'LOGGED_OFF' ? 'm' : 'g'}>{r.status}</Pill>]]} />
      </>}
      {tab === 'wc' && <>
        <CrudCard title="Work centers" sub="Packing, VAS, quality or deconsolidation stations" path={P('work-centers')} sing="work center"
          fields={[code, name, { k: 'kind', l: 'Kind', t: 'sel', o: () => [['PACK', 'Packing'], ['VAS', 'Value-added services'], ['QUAL', 'Quality'], ['DECO', 'Deconsolidation']], d: 'PACK' },
            { k: 'bin_id', l: 'Work center bin', t: 'sel', num: true, o: nonStorage }]} />
        <CrudCard title="Doors" sub="Loading / unloading doors, each linked to a staging-lane bin" path={P('doors')} sing="door"
          fields={[code, name, { k: 'direction', l: 'Direction', t: 'sel', o: () => [['IN', 'Inbound'], ['OUT', 'Outbound'], ['BOTH', 'Both']], d: 'IN' },
            { k: 'bin_id', l: 'Staging lane bin', t: 'sel', num: true, o: nonStorage }]} />
      </>}
    </>
  )
}
