import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Field, Note, fmt, useLoad } from '../ui.jsx'

const CW = 44, CH = 32, G = 4, P = 26
const PAL = ['#3B82C4', '#2E9E8F', '#8A5CC9', '#C98A2E', '#C4566B', '#5C8A3B', '#4A6FD6', '#B8694A', '#6B7F99', '#9A4FA8']
const tint = c => `color-mix(in srgb, ${c} 50%, var(--surface))`
const LENS = { stype: ['Storage type', 'storage_type_id', 'st'], section: ['Section', 'section_id', 'sec'],
  bintype: ['Bin type', 'bin_type_id', 'bt'], aarea: ['Activity area', 'activity_area_id', 'aa'] }
const STATUS_COLOR = { new: 'var(--accent)', exists: 'var(--ok)' }
const pad2 = n => String(n).padStart(2, '0')

function rackFootprint(r) {
  const horiz = Math.abs(r.x2 - r.x1) >= Math.abs(r.y2 - r.y1)
  const len = Math.min(200, (horiz ? Math.abs(r.x2 - r.x1) : Math.abs(r.y2 - r.y1)) + 1)
  const dp = Math.sign(horiz ? r.x2 - r.x1 : r.y2 - r.y1) || 1
  const na = Math.max(1, Math.min(40, r.aisle_to - r.aisle_from + 1)), gap = Math.max(1, r.aisle_gap || 1)
  const out = []
  for (let a = 0; a < na; a++) for (let i = 0; i < len; i++)
    out.push(horiz ? [r.x1 + i * dp, r.y1 + a * gap] : [r.x1 + a * gap, r.y1 + i * dp])
  return out
}

export default function Designer() {
  const { whId, can, run } = useApp()
  const ed = can('setup')
  const [params, setParams] = useSearchParams()
  const W = p => api.get(`/warehouses/${whId}/${p}`)
  const [bins, rBins] = useLoad(() => W('bins'), [whId])
  const [st] = useLoad(() => W('storage-types'), [whId])
  const [sec] = useLoad(() => W('sections'), [whId])
  const [bt] = useLoad(() => W('bin-types'), [whId])
  const [aa] = useLoad(() => W('activity-areas'), [whId])
  const [racks, rRacks] = useLoad(() => W('racks'), [whId])
  const lists = { st, sec, bt, aa }

  const [mode, setMode] = useState('select')
  const [lens, setLens] = useState('stype')
  const [level, setLevel] = useState(1)
  const [sel, setSel] = useState(new Set())
  const [allLv, setAllLv] = useState(true)
  const [grow, setGrow] = useState([0, 0])
  const [dragRect, setDragRect] = useState(null)
  const drag = useRef(null)
  const svgRef = useRef(null)
  const [draw, setDraw] = useState({ storage_type_id: null, section_id: null, bin_type_id: null, activity_area_id: null, levels: 1, prefix: '', pick_face: false })
  const [rack, setRack] = useState(null)
  const [preview, setPreview] = useState(null)
  const [assign, setAssign] = useState({})

  const newRack = (stId) => {
    const s = (st || []).find(x => x.id === stId) || (st || []).find(x => x.role === 'STORAGE') || (st || [])[0]
    const y = bins?.length ? Math.max(...bins.map(b => b.y)) + 2 : 0
    let n = (racks || []).length + 1
    while ((racks || []).some(r => r.code === 'RACK-' + pad2(n))) n++
    return { code: 'RACK-' + pad2(n), name: '', storage_type_id: s?.id ?? null, section_id: null, bin_type_id: null, activity_area_id: null,
      pick_face: false, x1: 0, y1: y, x2: 7, y2: y, aisle_from: 1, aisle_to: 1, aisle_gap: 1, pos_from: 1, pos_step: 1,
      level_from: 1, level_to: 3, pattern: '{ST}-{A}-{P}-{L}', pad: 2 }
  }

  // deep links from Organisation: ?focus=section:12  ?rack=5  ?rack=new&st=3
  useEffect(() => {
    if (!bins || !st || !racks) return
    const focus = params.get('focus'), rk = params.get('rack')
    if (focus) {
      const [kind, id] = focus.split(':'), n = Number(id)
      const f = { stype: b => b.storage_type_id === n, section: b => b.section_id === n, aarea: b => b.activity_area_id === n,
        nosec: b => b.role === 'STORAGE' && !b.section_id, nobt: b => !b.bin_type_id, noaa: b => !b.activity_area_id }[kind]
      const hit = f ? bins.filter(f) : []
      const lv = hit.length ? Math.min(...hit.map(b => b.z)) : 1
      setMode('select'); setLevel(lv); setSel(new Set(hit.filter(b => b.z === lv).map(b => b.id)))
      setLens({ stype: 'stype', section: 'section', nosec: 'section', nobt: 'bintype', aarea: 'aarea', noaa: 'aarea' }[kind] || 'stype')
      setParams({}, { replace: true })
    } else if (rk) {
      const ex = racks.find(r => String(r.id) === rk)
      setRack(ex ? { ...ex } : newRack(Number(params.get('st')) || null))
      setMode('rack'); setLevel(ex ? ex.level_from : 1); setParams({}, { replace: true })
    }
  }, [bins, st, racks])

  useEffect(() => { if (mode === 'rack' && !rack && st && bins) setRack(newRack()) }, [mode, st, bins])
  useEffect(() => { if (!draw.storage_type_id && st?.length) setDraw(d => ({ ...d, storage_type_id: (st.find(x => x.role === 'STORAGE') || st[0]).id })) }, [st])

  // server-side rack preview (debounced) — the middleware is the single source of truth for codes and conflicts
  useEffect(() => {
    if (mode !== 'rack' || !rack?.storage_type_id) return
    const t = setTimeout(() => api.post(`/warehouses/${whId}/racks/preview`, { ...rack, code: rack.code || 'PREVIEW' })
      .then(setPreview).catch(() => setPreview(null)), 220)
    return () => clearTimeout(t)
  }, [rack, mode, bins])

  const geom = useMemo(() => {
    const mx = Math.max(0, ...(bins || []).map(b => b.x)), my = Math.max(0, ...(bins || []).map(b => b.y))
    let rx = 0, ry = 0
    if (mode === 'rack' && rack) rackFootprint(rack).forEach(([x, y]) => { rx = Math.max(rx, x); ry = Math.max(ry, y) })
    return { cols: Math.max(18, mx + 5, rx + 4) + grow[0], rows: Math.max(10, my + 4, ry + 3) + grow[1] }
  }, [bins, mode, rack, grow])

  if (!bins || !st) return <Card><div className="empty">Loading layout…</div></Card>
  if (!st.length) return <Card><div className="empty">Create a storage type first (Organisation → Storage types & sections).</div></Card>

  const levels = [...new Set(bins.map(b => b.z))].sort((a, b) => a - b)
  const lvOpts = [...new Set([...levels, level, (levels.length ? Math.max(...levels) : 0) + 1])].sort((a, b) => a - b)
  const onLevel = bins.filter(b => b.z === level)
  const [lensLabel, lensKey, lensList] = LENS[lens]
  const lensRows = lists[lensList] || []
  const colorOf = b => { const i = lensRows.findIndex(x => x.id === b[lensKey]); return i < 0 ? 'var(--surface)' : tint(PAL[i % PAL.length]) }
  const W2 = P * 2 + geom.cols * (CW + G), H2 = P * 2 + geom.rows * (CH + G)

  const cellOf = e => {
    const svg = svgRef.current, pt = svg.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM().inverse())
    return { x: Math.max(0, Math.min(geom.cols - 1, Math.floor((p.x - P) / (CW + G)))), y: Math.max(0, Math.min(geom.rows - 1, Math.floor((p.y - P) / (CH + G)))) }
  }
  const onDown = e => {
    if (e.button > 0) return
    const c = cellOf(e)
    svgRef.current.setPointerCapture(e.pointerId)
    if (mode === 'rack') { drag.current = { rack: true }; setRack(r => ({ ...r, x1: c.x, y1: c.y, x2: c.x, y2: c.y })); return }
    drag.current = { x0: c.x, y0: c.y, x1: c.x, y1: c.y, add: e.shiftKey }; setDragRect({ ...drag.current })
  }
  const onMove = e => {
    const d = drag.current; if (!d) return
    const c = cellOf(e)
    if (d.rack) { setRack(r => Math.abs(c.x - r.x1) >= Math.abs(c.y - r.y1) ? { ...r, x2: c.x, y2: r.y1 } : { ...r, x2: r.x1, y2: c.y }); return }
    if (c.x !== d.x1 || c.y !== d.y1) { d.x1 = c.x; d.y1 = c.y; setDragRect({ ...d }) }
  }
  const onUp = async () => {
    const d = drag.current; drag.current = null; setDragRect(null)
    if (!d || d.rack) return
    const x0 = Math.min(d.x0, d.x1), x1 = Math.max(d.x0, d.x1), y0 = Math.min(d.y0, d.y1), y1 = Math.max(d.y0, d.y1)
    if (mode === 'draw') {
      if (!ed) return
      const r = await run(() => api.post(`/warehouses/${whId}/designer/draw`, { ...draw, x0, y0, x1, y1, level }),
        x => x.made ? `${x.made} bins created${x.skipped ? ` · ${x.skipped} cells already taken` : ''}` : 'Those cells are already taken')
      if (r) rBins()
      return
    }
    const hit = onLevel.filter(b => b.x >= x0 && b.x <= x1 && b.y >= y0 && b.y <= y1)
    setSel(prev => {
      const s = new Set(d.add ? prev : [])
      if (x0 === x1 && y0 === y1) { const p = new Set(prev); hit.forEach(b => (p.has(b.id) ? p.delete(b.id) : p.add(b.id))); return hit.length ? p : (d.add ? prev : new Set()) }
      hit.forEach(b => s.add(b.id)); return s
    })
  }

  // selection expanded to all levels at the same x/y
  const selBins = (() => {
    const ids = bins.filter(b => sel.has(b.id))
    if (!allLv) return ids
    const pos = new Set(ids.map(b => b.x + ',' + b.y))
    return bins.filter(b => pos.has(b.x + ',' + b.y))
  })()
  const doAssign = async () => {
    const body = { bin_ids: selBins.map(b => b.id), all_levels: false }
    for (const k of ['storage_type_id', 'section_id', 'bin_type_id', 'activity_area_id']) if (assign[k] !== undefined && assign[k] !== '') body[k] = Number(assign[k])
    if (assign.pick_face) body.pick_face = assign.pick_face === '1'
    if (assign.blocked) body.blocked = assign.blocked === '1'
    if (await run(() => api.post(`/warehouses/${whId}/designer/assign`, body), x => `${x.updated} bins updated${x.skipped ? ` · ${x.skipped} skipped (stock, or section of another storage type)` : ''}`)) { setAssign({}); rBins() }
  }
  const doDelete = async () => {
    if (!confirm(`Delete the empty bins among ${selBins.length} selected?`)) return
    if (await run(() => api.post(`/warehouses/${whId}/designer/delete`, { ids: selBins.map(b => b.id) }), x => `${x.deleted} bins deleted${x.kept_with_stock ? ` · ${x.kept_with_stock} kept (stock)` : ''}`)) { setSel(new Set()); rBins() }
  }
  const saveRack = async generate => {
    const body = { ...rack }
    const path = rack.id ? `/warehouses/${whId}/racks/${rack.id}?generate=${generate}` : `/warehouses/${whId}/racks?generate=${generate}`
    const r = await run(() => (rack.id ? api.put(path, body) : api.post(path, body)),
      x => generate ? `${x.made} bins generated${x.skipped ? ` · ${x.skipped} conflicts skipped` : ''}` : 'Rack saved')
    if (r) { setRack({ ...rack, id: r.id }); rRacks(); rBins() }
  }

  // rack ghost cells, coloured by the server preview status (worst status per cell)
  const ghost = mode === 'rack' && rack ? (() => {
    const st_ = {}
    const rank = { out: 5, code: 4, pos: 4, dup: 4, new: 2, exists: 1 }
    ;(preview?.items || []).forEach(it => { const k = it.x + ',' + it.y; if (!st_[k] || rank[it.status] > rank[st_[k]]) st_[k] = it.status })
    return rackFootprint(rack).filter(([x, y]) => x >= 0 && y >= 0).map(([x, y]) => {
      const s = st_[x + ',' + y], c = STATUS_COLOR[s] || (s ? 'var(--danger)' : 'var(--accent)')
      return <rect key={'g' + x + ',' + y} x={P + x * (CW + G) + 1} y={P + y * (CH + G) + 1} width={CW - 2} height={CH - 2} rx={4} pointerEvents="none"
        fill={`color-mix(in srgb, ${c} 16%, transparent)`} stroke={c} strokeWidth={1.6} strokeDasharray="4 2" />
    })
  })() : null
  const marker = (x, y, t) => <g key={t} pointerEvents="none"><circle cx={P + x * (CW + G) + CW / 2} cy={P + y * (CH + G) + CH / 2} r={9} fill="var(--accent)" />
    <text x={P + x * (CW + G) + CW / 2} y={P + y * (CH + G) + CH / 2 + 3.5} textAnchor="middle" fontSize={10} fontWeight={800} fill="#fff">{t}</text></g>

  const sel_ = (v, set, rows, none = '— none —') => (
    <select value={v ?? ''} onChange={e => set(e.target.value === '' ? null : Number(e.target.value))}>
      <option value="">{none}</option>{(rows || []).map(r => <option key={r.id} value={r.id}>{r.code} — {r.name}</option>)}</select>)
  const num = (v, set) => <input type="number" value={v} onChange={e => set(Math.round(Number(e.target.value) || 0))} />
  const R = (k, v) => setRack(r => ({ ...r, [k]: v }))

  return (
    <>
      <Card>
        <div className="row">
          <div className="segc">{[['select', 'Select & assign'], ['draw', 'Draw bins'], ['rack', 'Rack (start → end)']].map(([k, l]) => (
            <button key={k} className={mode === k ? 'on' : ''} disabled={k === 'draw' && !ed} onClick={() => setMode(k)}>{l}</button>))}</div>
          <Field label="Colour by" w={170}><select value={lens} onChange={e => setLens(e.target.value)}>
            {Object.entries(LENS).map(([k, v]) => <option key={k} value={k}>{v[0]}</option>)}</select></Field>
          <Field label="Level (Z)" w={130}><select value={level} onChange={e => { setLevel(Number(e.target.value)); setSel(new Set()) }}>
            {lvOpts.map(l => <option key={l} value={l}>Level {l}{levels.includes(l) ? '' : ' (new)'}</option>)}</select></Field>
          <div className="spacer" />
          <button className="btn sm" onClick={() => setGrow(([a, b]) => [a + 6, b])}>+ Columns</button>
          <button className="btn sm" onClick={() => setGrow(([a, b]) => [a, b + 4])}>+ Rows</button>
        </div>
      </Card>
      <div className="dz-main">
        <Card style={{ marginBottom: 0 }}>
          <div className="dz-canvas">
            <svg ref={svgRef} className={'dzsvg ' + mode} viewBox={`0 0 ${W2} ${H2}`} width={W2} height={H2}
              onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => { drag.current = null; setDragRect(null) }}>
              {Array.from({ length: geom.rows * geom.cols }, (_, i) => {
                const x = i % geom.cols, y = Math.floor(i / geom.cols)
                return <rect key={i} className="gcell" x={P + x * (CW + G)} y={P + y * (CH + G)} width={CW} height={CH} rx={3} />
              })}
              {Array.from({ length: geom.cols }, (_, x) => <text key={'ax' + x} className="ax" x={P + x * (CW + G) + CW / 2} y={P - 8}>{x}</text>)}
              {Array.from({ length: geom.rows }, (_, y) => <text key={'ay' + y} className="ax" x={P - 10} y={P + y * (CH + G) + CH / 2 + 3}>{y}</text>)}
              {onLevel.map(b => {
                const x = P + b.x * (CW + G), y = P + b.y * (CH + G)
                const lbl = b.code.length > 15 ? '…' + b.code.slice(-14) : b.code
                const fs = Math.min(7.5, (CW - 4) / (lbl.length * 0.62))
                return (
                  <g key={b.id} className={'dbin' + (sel.has(b.id) ? ' sel' : '')}>
                    <rect x={x} y={y} width={CW} height={CH} rx={4} fill={colorOf(b)} />
                    {b.blocked && <line x1={x + 3} y1={y + 3} x2={x + CW - 3} y2={y + CH - 3} stroke="var(--danger)" strokeWidth={1.5} />}
                    {b.pick_face && <circle cx={x + CW - 6} cy={y + 6} r={2.6} fill="var(--accent)" />}
                    <text x={x + CW / 2} y={y + 13} style={{ fontSize: fs }}>{lbl}</text>
                    <text x={x + CW / 2} y={y + 24} className="sm">{b.qty ? fmt(b.qty) : ''}</text>
                    <title>{`${b.code} · ${st.find(s => s.id === b.storage_type_id)?.code || ''} · fill ${Math.round(b.fill * 100)}%`}</title>
                  </g>)
              })}
              {ghost}
              {mode === 'rack' && rack && <>{marker(rack.x1, rack.y1, 'S')}{marker(rack.x2, rack.y2, 'E')}</>}
              {dragRect && (() => { const x0 = Math.min(dragRect.x0, dragRect.x1), x1 = Math.max(dragRect.x0, dragRect.x1), y0 = Math.min(dragRect.y0, dragRect.y1), y1 = Math.max(dragRect.y0, dragRect.y1)
                return <rect className="dzr" x={P + x0 * (CW + G) - 2} y={P + y0 * (CH + G) - 2} width={(x1 - x0 + 1) * (CW + G) - G + 4} height={(y1 - y0 + 1) * (CH + G) - G + 4} /> })()}
            </svg>
          </div>
          <div className="legend">{lensRows.map((o, i) => <span key={o.id}><i className="sw" style={{ background: tint(PAL[i % PAL.length]) }} />{o.code}</span>)}
            <span><i className="sw" style={{ background: 'var(--surface)' }} />Not assigned</span>
            <span><i className="sw" style={{ background: 'var(--accent)', borderRadius: '50%' }} />Pick face</span></div>
          <Note>{mode === 'rack' ? 'Drag from the START cell to the END cell (snaps to a straight line). Dashed boxes are the preview — blue new, green already generated, red conflict.'
            : mode === 'draw' ? 'Drag over empty cells — one bin per cell (and per level if levels > 1).' : 'Click a bin to select · drag to select an area · Shift + drag adds to the selection.'}</Note>
        </Card>

        <Card style={{ marginBottom: 0 }}>
          {mode === 'select' && <>
            <h3>{selBins.length} bins selected</h3>
            <div className="sub" style={{ marginBottom: 8 }}>{selBins.length ? selBins.slice(0, 8).map(b => b.code).join(', ') + (selBins.length > 8 ? ' …' : '') : 'Select bins on the grid'}</div>
            <div className="row" style={{ marginBottom: 9 }}>
              <button className="btn sm" onClick={() => setSel(new Set(onLevel.map(b => b.id)))}>Select level</button>
              <button className="btn sm" disabled={!sel.size} onClick={() => setSel(new Set())}>Clear</button></div>
            <label className="ck"><input type="checkbox" checked={allLv} onChange={e => setAllLv(e.target.checked)} /> Same position on all levels</label>
            {[['storage_type_id', 'Storage type', st, false], ['section_id', 'Section', sec, true], ['bin_type_id', 'Bin type', bt, true], ['activity_area_id', 'Activity area', aa, true]].map(([k, l, rows, clr]) => (
              <div key={k} style={{ marginTop: 9 }}><label>{l}</label>
                <select disabled={!ed || !selBins.length} value={assign[k] ?? ''} onChange={e => setAssign(a => ({ ...a, [k]: e.target.value }))}>
                  <option value="">— keep —</option>{clr && <option value="0">— clear —</option>}
                  {(rows || []).map(r => <option key={r.id} value={r.id}>{k === 'section_id' ? `${st.find(s => s.id === r.storage_type_id)?.code} / ${r.code}` : r.code} — {r.name}</option>)}</select></div>))}
            <div className="row" style={{ marginTop: 9 }}>
              <Field label="Role"><select disabled={!ed || !selBins.length} value={assign.pick_face ?? ''} onChange={e => setAssign(a => ({ ...a, pick_face: e.target.value }))}>
                <option value="">— keep —</option><option value="0">Bulk</option><option value="1">Pick face</option></select></Field>
              <Field label="Status"><select disabled={!ed || !selBins.length} value={assign.blocked ?? ''} onChange={e => setAssign(a => ({ ...a, blocked: e.target.value }))}>
                <option value="">— keep —</option><option value="0">Open</option><option value="1">Blocked</option></select></Field></div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn p" disabled={!ed || !selBins.length} onClick={doAssign}>Apply to {selBins.length} bins</button>
              <button className="btn d" disabled={!ed || !selBins.length} onClick={doDelete}>Delete empty</button></div>
            {!ed && <Note tone="warn">Switch to the Admin role to change bins.</Note>}
          </>}

          {mode === 'draw' && <>
            <h3>Draw bins</h3><div className="sub" style={{ marginBottom: 8 }}>Starting at level {level}</div>
            <label>Storage type</label>{sel_(draw.storage_type_id, v => setDraw(d => ({ ...d, storage_type_id: v, section_id: null })), st, '— choose —')}
            <div style={{ marginTop: 8 }}><label>Section</label>{sel_(draw.section_id, v => setDraw(d => ({ ...d, section_id: v })), (sec || []).filter(s => s.storage_type_id === draw.storage_type_id))}</div>
            <div style={{ marginTop: 8 }}><label>Bin type</label>{sel_(draw.bin_type_id, v => setDraw(d => ({ ...d, bin_type_id: v })), bt, '— none (100 qty) —')}</div>
            <div style={{ marginTop: 8 }}><label>Activity area</label>{sel_(draw.activity_area_id, v => setDraw(d => ({ ...d, activity_area_id: v })), aa)}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <Field label="Levels">{num(draw.levels, v => setDraw(d => ({ ...d, levels: Math.max(1, Math.min(9, v)) })))}</Field>
              <Field label="Code prefix"><input value={draw.prefix} placeholder={st.find(s => s.id === draw.storage_type_id)?.code}
                onChange={e => setDraw(d => ({ ...d, prefix: e.target.value.toUpperCase() }))} /></Field></div>
            <label className="ck" style={{ marginTop: 10 }}><input type="checkbox" checked={draw.pick_face} onChange={e => setDraw(d => ({ ...d, pick_face: e.target.checked }))} /> Pick face bins (replenished)</label>
          </>}

          {mode === 'rack' && rack && <>
            <h3>Rack — start to end point</h3>
            <div className="sub" style={{ marginBottom: 8 }}>Drag S → E on the grid, or type the coordinates</div>
            <label>Rack</label>
            <select value={rack.id || ''} onChange={e => { const ex = racks.find(r => r.id === Number(e.target.value)); setRack(ex ? { ...ex } : newRack()); if (ex) setLevel(ex.level_from) }}>
              <option value="">+ New rack</option>{(racks || []).map(r => <option key={r.id} value={r.id}>{r.code}{r.name ? ' — ' + r.name : ''}</option>)}</select>
            <div className="row" style={{ marginTop: 8 }}>
              <Field label="Rack code"><input value={rack.code} onChange={e => R('code', e.target.value.toUpperCase())} /></Field>
              <Field label="Description"><input value={rack.name} onChange={e => R('name', e.target.value)} /></Field></div>
            <div style={{ marginTop: 8 }}><label>Storage type</label>{sel_(rack.storage_type_id, v => setRack(r => ({ ...r, storage_type_id: v, section_id: null })), st, '— choose —')}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <Field label="Section">{sel_(rack.section_id, v => R('section_id', v), (sec || []).filter(s => s.storage_type_id === rack.storage_type_id))}</Field>
              <Field label="Bin type">{sel_(rack.bin_type_id, v => R('bin_type_id', v), bt)}</Field></div>
            <div style={{ marginTop: 8 }}><label>Activity area</label>{sel_(rack.activity_area_id, v => R('activity_area_id', v), aa)}</div>
            <div className="rkbox">
              <div className="row"><Field label="Start point X">{num(rack.x1, v => R('x1', Math.max(0, v)))}</Field><Field label="Start point Y">{num(rack.y1, v => R('y1', Math.max(0, v)))}</Field></div>
              <div className="row" style={{ marginTop: 6 }}><Field label="End point X">{num(rack.x2, v => R('x2', Math.max(0, v)))}</Field><Field label="End point Y">{num(rack.y2, v => R('y2', Math.max(0, v)))}</Field></div></div>
            <div className="row" style={{ marginTop: 8 }}><Field label="Aisle from">{num(rack.aisle_from, v => R('aisle_from', v))}</Field>
              <Field label="Aisle to">{num(rack.aisle_to, v => R('aisle_to', Math.max(rack.aisle_from, v)))}</Field>
              <Field label="Aisle gap">{num(rack.aisle_gap, v => R('aisle_gap', Math.max(1, v)))}</Field></div>
            <div className="row" style={{ marginTop: 8 }}><Field label="Position start">{num(rack.pos_from, v => R('pos_from', v))}</Field>
              <Field label="Position step">{num(rack.pos_step, v => R('pos_step', Math.max(1, v)))}</Field></div>
            <div className="row" style={{ marginTop: 8 }}><Field label="Level from">{num(rack.level_from, v => R('level_from', v))}</Field>
              <Field label="Level to">{num(rack.level_to, v => R('level_to', Math.max(rack.level_from, v)))}</Field></div>
            <div className="row" style={{ marginTop: 8 }}><Field label="Code pattern"><input value={rack.pattern} onChange={e => R('pattern', e.target.value)} /></Field>
              <Field label="Digits" w={70}>{num(rack.pad, v => R('pad', Math.max(1, Math.min(5, v))))}</Field></div>
            <div className="sub" style={{ marginTop: 4 }}>{'{ST}'} storage type · {'{SEC}'} section · {'{A}'} aisle · {'{P}'} position · {'{L}'} level · {'{P3}'} = 3 digits</div>
            <label className="ck" style={{ marginTop: 9 }}><input type="checkbox" checked={rack.pick_face} onChange={e => R('pick_face', e.target.checked)} /> Pick face bins</label>
            {preview && <Note>
              {preview.aisles} aisle(s) × {preview.positions} positions × {preview.levels} level(s) = <b>{preview.items.length} bins</b> · {preview.horizontal ? 'horizontal' : 'vertical'}<br />
              <span className="mono">{preview.items[0]?.code}</span> … <span className="mono">{preview.items[preview.items.length - 1]?.code}</span><br />
              <b style={{ color: 'var(--accent)' }}>{preview.counts.new || 0} new</b>
              {preview.counts.exists ? <span style={{ color: 'var(--ok)' }}> · {preview.counts.exists} already generated</span> : null}
              {preview.conflicts.length ? <b style={{ color: 'var(--danger)' }}> · {preview.items.length - (preview.counts.new || 0) - (preview.counts.exists || 0)} conflicts</b> : null}
              {preview.conflicts.slice(0, 4).map(c => <div key={c.code}><span className="mono">{c.code}</span> — {c.why}</div>)}
            </Note>}
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn p" disabled={!ed || !preview?.counts.new} onClick={() => saveRack(true)}>Generate {preview?.counts.new || 0} bins</button>
              <button className="btn" disabled={!ed} onClick={() => saveRack(false)}>Save rack</button></div>
            {!ed && <Note tone="warn">Switch to the Admin role to generate bins.</Note>}
          </>}
        </Card>
      </div>
    </>
  )
}
