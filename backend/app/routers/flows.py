"""Inbound (ASN), outbound (orders, waves), documents, warehouse tasks, warehouse orders, resources, audit."""
from datetime import datetime, date
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models as m, schemas as s
from ..core import get_role, require, to_dict, rows, get_or_404, next_number, BizError
from ..services.engine import WhCtx

r = APIRouter(prefix="/warehouses/{wh}", tags=["execution"])


def _check_lines(ctx: WhCtx, lines):
    for l in lines:
        mat = ctx.mats.get(l.material_id)
        if mat is None:
            raise BizError(f"Unknown material {l.material_id}")
        trk = getattr(l, "trk", "")
        if mat.tracking != "NONE" and hasattr(l, "trk") and not trk:
            raise BizError(f"{mat.code} needs a {'serial' if mat.tracking == 'SERIAL' else 'batch'} number")
        if mat.tracking == "SERIAL" and l.qty != 1 and hasattr(l, "trk"):
            raise BizError(f"{mat.code} is serial-managed — one line per serial with qty 1")


# ── inbound ──
@r.get("/asns")
def list_asns(wh: int, db: Session = Depends(get_db)):
    out = []
    for a in db.scalars(select(m.Asn).where(m.Asn.warehouse_id == wh).order_by(m.Asn.id.desc())):
        d = to_dict(a)
        d["lines"] = rows(db.scalars(select(m.AsnLine).where(m.AsnLine.asn_id == a.id)))
        out.append(d)
    return out


@r.post("/asns")
def create_asn(wh: int, body: s.AsnIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "create")
    ctx = WhCtx(db, wh, role)
    _check_lines(ctx, body.lines)
    a = m.Asn(warehouse_id=wh, number=next_number(db, wh, "ASN", "ASN"), vendor=body.vendor or "Vendor", eta=body.eta or date.today())
    db.add(a)
    db.flush()
    for l in body.lines:
        db.add(m.AsnLine(asn_id=a.id, material_id=l.material_id, qty=l.qty, tracking_no=l.trk, expiry=l.expiry))
    ctx.log("ASN", f"{a.number} created")
    db.commit()
    return to_dict(a)


@r.post("/asns/{asn_id}/receive")
def receive_asn(wh: int, asn_id: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "release")
    ctx = WhCtx(db, wh, role)
    res = ctx.receive_asn(get_or_404(db, m.Asn, asn_id, wh))
    db.commit()
    return res


# ── outbound ──
@r.get("/orders")
def list_orders(wh: int, db: Session = Depends(get_db)):
    out = []
    for o in db.scalars(select(m.SalesOrder).where(m.SalesOrder.warehouse_id == wh).order_by(m.SalesOrder.id.desc())):
        d = to_dict(o)
        d["lines"] = rows(db.scalars(select(m.SalesOrderLine).where(m.SalesOrderLine.order_id == o.id)))
        w = db.get(m.Wave, o.wave_id) if o.wave_id else None
        d["wave_number"] = w.number if w else None
        out.append(d)
    return out


@r.post("/orders")
def create_order(wh: int, body: s.OrderIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "create")
    ctx = WhCtx(db, wh, role)
    _check_lines(ctx, body.lines)
    o = m.SalesOrder(warehouse_id=wh, number=next_number(db, wh, "SO", "SO"), customer=body.customer or "Customer",
                     order_date=body.order_date or date.today())
    db.add(o)
    db.flush()
    for l in body.lines:
        db.add(m.SalesOrderLine(order_id=o.id, material_id=l.material_id, qty=l.qty))
    ctx.log("ORDER", f"{o.number} created")
    db.commit()
    return to_dict(o)


@r.post("/waves")
def create_wave(wh: int, body: s.WaveIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "release")
    ctx = WhCtx(db, wh, role)
    doc = ctx.create_wave(body.order_ids)
    db.commit()
    return {"document_id": doc.id, "document": doc.number}


# ── documents & warehouse tasks ──
def _task_out(ctx: WhCtx, t: m.WarehouseTask, doc: m.WtDocument, wo_numbers: dict) -> dict:
    d = to_dict(t)
    mat = ctx.mats.get(t.material_id)
    b = lambda i: ctx.bins[i].code if i and i in ctx.bins else None
    d.update(material_code=mat.code if mat else "?", material_name=mat.name if mat else "", doc_number=doc.number,
             doc_type=doc.type, source_bin=b(t.source_bin_id) or ("GR" if doc.type == "PUTAWAY" else None),
             dest_bin=b(t.dest_bin_id) or ("GI" if doc.type == "PICK" else None), wo_number=wo_numbers.get(t.wo_id))
    return d


@r.get("/documents")
def list_documents(wh: int, db: Session = Depends(get_db)):
    out = []
    for d in db.scalars(select(m.WtDocument).where(m.WtDocument.warehouse_id == wh).order_by(m.WtDocument.id.desc())):
        x = to_dict(d)
        x["tasks"] = db.scalar(select(func.count()).select_from(m.WarehouseTask).where(m.WarehouseTask.document_id == d.id))
        x["done"] = db.scalar(select(func.count()).select_from(m.WarehouseTask).where(
            m.WarehouseTask.document_id == d.id, m.WarehouseTask.status == "CONFIRMED"))
        x["shortages"] = db.scalar(select(func.count()).select_from(m.DocumentShortage).where(m.DocumentShortage.document_id == d.id))
        out.append(x)
    return out


@r.get("/documents/{doc_id}")
def get_document(wh: int, doc_id: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    d = get_or_404(db, m.WtDocument, doc_id, wh)
    wos = {w.id: w.number for w in db.scalars(select(m.WarehouseOrder).where(m.WarehouseOrder.document_id == d.id))}
    x = to_dict(d)
    x["tasks"] = [_task_out(ctx, t, d, wos) for t in ctx.tasks_of(d.id)]
    x["shortages"] = [{**to_dict(sh), "material_code": ctx.mats[sh.material_id].code}
                      for sh in db.scalars(select(m.DocumentShortage).where(m.DocumentShortage.document_id == d.id))]
    x["stage_bin"] = ctx.bins[d.stage_bin_id].code if d.stage_bin_id in ctx.bins else None
    return x


@r.get("/tasks")
def list_tasks(wh: int, status: str = "OPEN", db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    q = select(m.WarehouseTask).where(m.WarehouseTask.warehouse_id == wh)
    if status:
        q = q.where(m.WarehouseTask.status == status)
    docs, wos = {}, {}
    out = []
    for t in db.scalars(q.order_by(m.WarehouseTask.wt_number.desc()).limit(500)):
        d = docs.setdefault(t.document_id, db.get(m.WtDocument, t.document_id))
        if t.wo_id and t.wo_id not in wos:
            wo = db.get(m.WarehouseOrder, t.wo_id)
            wos[t.wo_id] = wo.number
        out.append(_task_out(ctx, t, d, wos))
    return out


@r.post("/tasks/confirm")
def confirm_tasks(wh: int, body: s.IdsIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "confirm")
    n = WhCtx(db, wh, role).confirm_tasks(body.ids)
    db.commit()
    return {"confirmed": n}


# ── warehouse orders & resources ──
def _wo_out(ctx, w: m.WarehouseOrder, resources) -> dict:
    db = ctx.db
    d = to_dict(w)
    ts = list(db.scalars(select(m.WarehouseTask).where(m.WarehouseTask.wo_id == w.id)))
    doc = db.get(m.WtDocument, w.document_id)
    q = db.get(m.Queue, w.queue_id) if w.queue_id else None
    rs = db.get(m.Resource, w.resource_id) if w.resource_id else None
    aa = db.get(m.ActivityArea, int(w.area_key)) if w.area_key.isdigit() else None
    st = ctx.types.get(int(w.area_key[3:])) if w.area_key.startswith("ST:") else None
    d.update(doc_number=doc.number if doc else "", tasks=len(ts), done=sum(t.status == "CONFIRMED" for t in ts),
             queue_code=q.code if q else None, resource_code=rs.code if rs else None,
             area=aa.code if aa else (f"{st.code} (no AA)" if st else w.area_key),
             minutes=int((w.done_at - w.started_at).total_seconds() // 60) if w.done_at and w.started_at else None,
             eligible=[x.id for x in resources if x.status == "AVAILABLE" and ctx.wo_eligible(w, x)] if w.status == "OPEN" else [],
             lines=[{"bin": ctx.bins[t.source_bin_id or t.dest_bin_id].code if (t.source_bin_id or t.dest_bin_id) in ctx.bins else "?",
                     "material": ctx.mats[t.material_id].code, "qty": t.qty, "done": t.status == "CONFIRMED"} for t in ts])
    return d


@r.get("/warehouse-orders")
def list_wos(wh: int, status: str = "", db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    res = list(db.scalars(select(m.Resource).where(m.Resource.warehouse_id == wh)))
    q = select(m.WarehouseOrder).where(m.WarehouseOrder.warehouse_id == wh)
    if status == "open":
        q = q.where(m.WarehouseOrder.status != "CONFIRMED")
    elif status:
        q = q.where(m.WarehouseOrder.status == status)
    return [_wo_out(ctx, w, res) for w in db.scalars(q.order_by(m.WarehouseOrder.id.desc()).limit(300))]


@r.post("/warehouse-orders/{wo_id}/assign")
def assign_wo(wh: int, wo_id: int, body: s.AssignIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "release")
    ctx = WhCtx(db, wh, role)
    ctx.wo_assign(get_or_404(db, m.WarehouseOrder, wo_id, wh), get_or_404(db, m.Resource, body.resource_id, wh))
    db.commit()
    return {"ok": True}


@r.post("/warehouse-orders/{wo_id}/unassign")
def unassign_wo(wh: int, wo_id: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "release")
    ctx = WhCtx(db, wh, role)
    wo = get_or_404(db, m.WarehouseOrder, wo_id, wh)
    if wo.status != "IN_PROCESS":
        raise BizError(f"{wo.number} is not in process")
    ctx.wo_release(wo)
    ctx.log("RSRC", f"{wo.number} unassigned")
    db.commit()
    return {"ok": True}


@r.post("/warehouse-orders/{wo_id}/confirm")
def confirm_wo(wh: int, wo_id: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "confirm")
    ctx = WhCtx(db, wh, role)
    ctx.wo_confirm(get_or_404(db, m.WarehouseOrder, wo_id, wh))
    db.commit()
    return {"ok": True}


@r.get("/resource-monitor")
def resource_monitor(wh: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    res = list(db.scalars(select(m.Resource).where(m.Resource.warehouse_id == wh).order_by(m.Resource.code)))
    open_wos = list(db.scalars(select(m.WarehouseOrder).where(m.WarehouseOrder.warehouse_id == wh, m.WarehouseOrder.status != "CONFIRMED")))
    queues = list(db.scalars(select(m.Queue).where(m.Queue.warehouse_id == wh).order_by(m.Queue.code)))
    on = [x for x in res if x.status != "LOGGED_OFF"]
    qrows = []
    for q in queues + [None]:
        ws = [w for w in open_wos if w.queue_id == (q.id if q else None)]
        if q is None and not ws:
            continue
        qrows.append({"id": q.id if q else None, "code": q.code if q else "(none)", "name": q.name if q else "No queue determined",
                      "waiting": sum(w.status == "OPEN" for w in ws), "in_process": sum(w.status == "IN_PROCESS" for w in ws),
                      "resources": sum(1 for x in on if not x.queue_ids or (q and q.id in x.queue_ids))})
    today0 = datetime.combine(date.today(), datetime.min.time())
    rout = []
    for x in res:
        done = list(db.scalars(select(m.WarehouseOrder).where(m.WarehouseOrder.resource_id == x.id, m.WarehouseOrder.status == "CONFIRMED",
                                                              m.WarehouseOrder.done_at >= today0)))
        mins = [int((w.done_at - w.started_at).total_seconds() // 60) for w in done if w.started_at]
        cur = db.get(m.WarehouseOrder, x.current_wo_id) if x.current_wo_id else None
        rt = db.get(m.ResourceType, x.resource_type_id) if x.resource_type_id else None
        rout.append({**to_dict(x), "type_code": rt.code if rt else None, "type_name": rt.name if rt else None,
                     "max_level": rt.max_level if rt else 0,
                     "queue_codes": [q.code for q in queues if q.id in (x.queue_ids or [])],
                     "current": _wo_out(ctx, cur, res) if cur else None, "done_today": len(done),
                     "avg_minutes": round(sum(mins) / len(mins)) if mins else None,
                     "eligible_waiting": sum(1 for w in open_wos if ctx.wo_eligible(w, x))})
    return {"queues": qrows, "resources": rout,
            "kpi": {"open_tasks": db.scalar(select(func.count()).select_from(m.WarehouseTask).where(
                        m.WarehouseTask.warehouse_id == wh, m.WarehouseTask.status == "OPEN")),
                    "open_wos": len(open_wos), "unassigned": sum(w.status == "OPEN" for w in open_wos),
                    "logged_on": len(on), "resources": len(res),
                    "confirmed_today": db.scalar(select(func.count()).select_from(m.WarehouseOrder).where(
                        m.WarehouseOrder.warehouse_id == wh, m.WarehouseOrder.status == "CONFIRMED", m.WarehouseOrder.done_at >= today0))}}


def _res(db, wh, rid):
    return get_or_404(db, m.Resource, rid, wh)


@r.post("/resources/{rid}/logon")
def logon(wh: int, rid: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "confirm")
    x = _res(db, wh, rid)
    x.status, x.current_wo_id = "AVAILABLE", None
    WhCtx(db, wh, role).log("RSRC", f"{x.code} logged on")
    db.commit()
    return {"ok": True}


@r.post("/resources/{rid}/logoff")
def logoff(wh: int, rid: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "confirm")
    ctx = WhCtx(db, wh, role)
    x = _res(db, wh, rid)
    if x.current_wo_id:
        wo = db.get(m.WarehouseOrder, x.current_wo_id)
        if wo and wo.status == "IN_PROCESS":
            ctx.wo_release(wo)
    x.status, x.current_wo_id = "LOGGED_OFF", None
    ctx.log("RSRC", f"{x.code} logged off")
    db.commit()
    return {"ok": True}


@r.post("/resources/{rid}/next")
def next_wo(wh: int, rid: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "confirm")
    ctx = WhCtx(db, wh, role)
    wo = ctx.wo_next(_res(db, wh, rid))
    db.commit()
    return {"wo": wo.number if wo else None}


@r.post("/resources/auto-assign")
def auto_assign(wh: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "release")
    ctx = WhCtx(db, wh, role)
    n = sum(1 for x in db.scalars(select(m.Resource).where(m.Resource.warehouse_id == wh, m.Resource.status == "AVAILABLE"))
            if ctx.wo_next(x))
    db.commit()
    return {"assigned": n}


@r.get("/audit")
def audit_log(wh: int, limit: int = 300, db: Session = Depends(get_db)):
    return rows(db.scalars(select(m.AuditLog).where(m.AuditLog.warehouse_id == wh).order_by(m.AuditLog.id.desc()).limit(limit)))
