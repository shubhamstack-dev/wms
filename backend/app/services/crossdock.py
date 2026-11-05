"""Planned (PXD) and transport (TCD) cross-docking: GR dock → GI dock without putaway."""
from datetime import datetime
from sqlalchemy import select
from .. import models as m
from ..core import BizError, next_number, utcnow
from .engine import WhCtx


def xd_bins(ctx: WhCtx):
    inb = ctx.bins.get(ctx.cfg.xd_in_bin_id) or ctx.first_bin("RECEIVING", "STAGING")
    outb = ctx.bins.get(ctx.cfg.xd_out_bin_id) or ctx.first_bin("SHIPPING", "STAGING")
    return inb, outb


def create_order(ctx: WhCtx, kind: str, from_party: str, to_party: str, lines: list[dict], transfer_id=None):
    if not lines:
        raise BizError("Add at least one line")
    xo = m.CrossdockOrder(warehouse_id=ctx.wh_id, number=next_number(ctx.db, ctx.wh_id, "XDO", "XDO"), kind=kind,
                          from_party=from_party or "Supplier", to_party=to_party or "Customer", transfer_id=transfer_id)
    ctx.db.add(xo)
    ctx.db.flush()
    for l in lines:
        mat = ctx.mats.get(l["material_id"])
        if mat is None:
            raise BizError("Unknown material")
        if mat.tracking != "NONE" and not l.get("trk"):
            raise BizError(f"{mat.code} needs a {'serial' if mat.tracking == 'SERIAL' else 'batch'} number")
        ctx.db.add(m.CrossdockOrderLine(order_id=xo.id, material_id=mat.id, qty=l["qty"], tracking_no=l.get("trk") or "",
                                        expiry=l.get("expiry")))
    ctx.log("XDOCK", f"{xo.number} planned ({kind})")
    return xo


def lines_of(ctx: WhCtx, xo):
    return list(ctx.db.scalars(select(m.CrossdockOrderLine).where(m.CrossdockOrderLine.order_id == xo.id)))


def receive(ctx: WhCtx, xo: m.CrossdockOrder) -> m.WtDocument:
    if xo.status != "PLANNED":
        raise BizError(f"{xo.number} is already {xo.status}")
    inb, outb = xd_bins(ctx)
    if not inb or not outb:
        raise BizError("Cross-docking needs a RECEIVING and a SHIPPING bin in this warehouse")
    tasks = []
    for l in lines_of(ctx, xo):
        mat = ctx.mats[l.material_id]
        s = ctx.add_stock(inb.id, mat.id, l.qty, *ctx.track_split(mat, l.tracking_no), l.expiry)
        tasks.append({"material_id": mat.id, "qty": l.qty, "trk": l.tracking_no, "expiry": l.expiry,
                      "source_bin_id": inb.id, "dest_bin_id": outb.id, "stock_id": s.id})
    doc = ctx.create_document("XDOCK", tasks, strategy="transport XD" if xo.kind == "TCD" else "planned XD",
                              source=f"Cross-dock {xo.number}")
    xo.document_id, xo.status, xo.received_at = doc.id, "IN_XDOCK", utcnow()
    ctx.log("XDOCK", f"{xo.number} received at {inb.code} → {doc.number} ({len(tasks)} moves to {outb.code})")
    return doc


def confirm_moves(ctx: WhCtx, xo: m.CrossdockOrder):
    if xo.status != "IN_XDOCK":
        raise BizError(f"{xo.number} is not on the dock")
    ctx.confirm_tasks([t.id for t in ctx.tasks_of(xo.document_id) if t.status == "OPEN"])


def goods_issue(ctx: WhCtx, xo: m.CrossdockOrder) -> list[dict]:
    if xo.status != "READY":
        raise BizError(f"{xo.number} is not ready to ship (status {xo.status})")
    shipped = []
    for t in ctx.tasks_of(xo.document_id):
        q = ctx.take_from(t.dest_bin_id, t.material_id, t.tracking_no, t.qty)
        shipped.append({"material_id": t.material_id, "qty": q, "trk": t.tracking_no, "expiry": t.expiry})
    xo.status, xo.shipped_at = "SHIPPED", utcnow()
    dwell = int((xo.shipped_at - xo.received_at).total_seconds() // 60) if xo.received_at else 0
    ctx.log("XD GI", f"{xo.number} goods issue to {xo.to_party} — {sum(s['qty'] for s in shipped):g} units, dwell {dwell} min")
    if xo.transfer_id:
        from .transfers import on_hub_dispatched
        on_hub_dispatched(ctx.db, ctx, xo, shipped)
    return shipped
