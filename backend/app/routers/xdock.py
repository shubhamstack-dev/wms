"""Cross-docking (planned + opportunistic log) per warehouse, and enterprise stock transfers (transport cross-docking)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models as m, schemas as s
from ..core import get_role, require, to_dict, rows, get_or_404, BizError
from ..services.engine import WhCtx
from ..services import crossdock, transfers

r = APIRouter(tags=["cross-docking"])


@r.get("/warehouses/{wh}/crossdock-orders")
def list_xd(wh: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    inb, outb = crossdock.xd_bins(ctx)
    out = []
    for xo in db.scalars(select(m.CrossdockOrder).where(m.CrossdockOrder.warehouse_id == wh).order_by(m.CrossdockOrder.id.desc())):
        d = to_dict(xo)
        d["lines"] = [{**to_dict(l), "material_code": ctx.mats[l.material_id].code} for l in crossdock.lines_of(ctx, xo)]
        if xo.document_id:
            ts = ctx.tasks_of(xo.document_id)
            doc = db.get(m.WtDocument, xo.document_id)
            d.update(doc_number=doc.number, tasks=len(ts), done=sum(t.status == "CONFIRMED" for t in ts))
        if xo.received_at and xo.shipped_at:
            d["dwell_minutes"] = int((xo.shipped_at - xo.received_at).total_seconds() // 60)
        out.append(d)
    return {"orders": out, "in_bin": inb.code if inb else None, "out_bin": outb.code if outb else None,
            "opportunistic": [{**to_dict(e), "material_code": ctx.mats[e.material_id].code,
                               "to_bin": ctx.bins[e.to_bin_id].code if e.to_bin_id in ctx.bins else "?"}
                              for e in db.scalars(select(m.XdockEvent).where(m.XdockEvent.warehouse_id == wh).order_by(m.XdockEvent.id.desc()))],
            "backorders": [{"document": d.number, "material_code": ctx.mats[sh.material_id].code, "qty": sh.qty}
                           for sh, d in db.execute(select(m.DocumentShortage, m.WtDocument).join(
                               m.WtDocument, m.WtDocument.id == m.DocumentShortage.document_id).where(
                               m.WtDocument.warehouse_id == wh, m.WtDocument.type == "PICK"))]}


@r.post("/warehouses/{wh}/crossdock-orders")
def create_xd(wh: int, body: s.XdOrderIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "create")
    xo = crossdock.create_order(WhCtx(db, wh, role), "PXD", body.from_party, body.to_party,
                                [l.model_dump() for l in body.lines])
    db.commit()
    return to_dict(xo)


def _xd_action(fn, perm):
    def handler(wh: int, xid: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, perm)
        ctx = WhCtx(db, wh, role)
        fn(ctx, get_or_404(db, m.CrossdockOrder, xid, wh))
        db.commit()
        return {"ok": True}
    return handler


r.post("/warehouses/{wh}/crossdock-orders/{xid}/receive")(_xd_action(crossdock.receive, "release"))
r.post("/warehouses/{wh}/crossdock-orders/{xid}/confirm-moves")(_xd_action(crossdock.confirm_moves, "confirm"))
r.post("/warehouses/{wh}/crossdock-orders/{xid}/goods-issue")(_xd_action(crossdock.goods_issue, "release"))


# ── enterprise stock transfers ──
@r.get("/transfers")
def list_transfers(db: Session = Depends(get_db)):
    codes = {w.id: w.code for w in db.scalars(select(m.Warehouse))}
    mats = {x.id: x.code for x in db.scalars(select(m.Material))}
    out = []
    for t in db.scalars(select(m.StockTransfer).order_by(m.StockTransfer.id.desc())):
        d = to_dict(t)
        d.update(from_code=codes.get(t.from_wh_id), via_code=codes.get(t.via_wh_id), to_code=codes.get(t.to_wh_id),
                 lines=[{"material_code": mats[l.material_id], "qty": l.qty}
                        for l in db.scalars(select(m.StockTransferLine).where(m.StockTransferLine.transfer_id == t.id))],
                 events=[to_dict(e) for e in db.scalars(select(m.StockTransferEvent).where(
                     m.StockTransferEvent.transfer_id == t.id).order_by(m.StockTransferEvent.id))])
        if t.source_order_id:
            o = db.get(m.SalesOrder, t.source_order_id)
            d["source_order"] = {"number": o.number, "status": o.status} if o else None
        if t.hub_xd_id:
            xo = db.get(m.CrossdockOrder, t.hub_xd_id)
            d["hub_xd"] = {"number": xo.number, "status": xo.status} if xo else None
        out.append(d)
    return out


@r.post("/transfers")
def create_transfer(body: s.TransferIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "create")
    t = transfers.create(db, role, body.from_wh_id, body.via_wh_id, body.to_wh_id, [l.model_dump() for l in body.lines])
    db.commit()
    return to_dict(t)


ACTIONS = {"release": (transfers.release, "release"), "pick-and-ship": (transfers.pick_and_ship, "release"),
           "hub-receive": (transfers.hub_receive_transfer, "release"), "hub-confirm": (transfers.hub_confirm, "confirm"),
           "hub-dispatch": (transfers.hub_dispatch, "release"), "receive": (transfers.receive_dest, "release")}


@r.post("/transfers/{tid}/{action}")
def transfer_action(tid: int, action: str, db: Session = Depends(get_db), role: str = Depends(get_role)):
    if action not in ACTIONS:
        raise BizError(f"Unknown action {action}")
    fn, perm = ACTIONS[action]
    require(role, perm)
    fn(db, get_or_404(db, m.StockTransfer, tid), role)
    db.commit()
    return {"ok": True}
