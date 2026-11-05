"""Stock transfers between warehouses, optionally via a cross-dock hub (transportation cross-docking).
Source: sales order → pick & ship.  Hub: ASN → cross-dock order (never putaway).  Destination: ASN → putaway."""
from datetime import datetime
from sqlalchemy import select
from .. import models as m
from ..core import BizError, next_number, utcnow
from .engine import WhCtx
from . import crossdock


def log(db, t: m.StockTransfer, msg: str):
    db.add(m.StockTransferEvent(transfer_id=t.id, message=msg[:300]))


def wh_code(db, wh_id):
    w = db.get(m.Warehouse, wh_id) if wh_id else None
    return w.code if w else "?"


def create(db, role: str, from_id: int, via_id: int | None, to_id: int, lines: list[dict]) -> m.StockTransfer:
    if from_id == to_id:
        raise BizError("Destination must be a different warehouse")
    if via_id in (from_id, to_id):
        via_id = None
    if not lines:
        raise BizError("Add at least one material")
    src = WhCtx(db, from_id, role)
    need = {}
    for l in lines:
        need[l["material_id"]] = need.get(l["material_id"], 0) + l["qty"]
    for mid, q in need.items():
        if q > src.mat_qty(mid) + 1e-9:
            raise BizError(f"{src.mats[mid].code}: only {src.mat_qty(mid):g} available in {src.wh.code}")
    t = m.StockTransfer(number=next_number(db, 0, "STO", "STO"), from_wh_id=from_id, via_wh_id=via_id, to_wh_id=to_id)
    db.add(t)
    db.flush()
    for mid, q in need.items():
        db.add(m.StockTransferLine(transfer_id=t.id, material_id=mid, qty=q))
    log(db, t, "Created: " + " → ".join(wh_code(db, w) for w in (from_id, via_id, to_id) if w))
    src.log("TRANSFER", f"{t.number} created")
    return t


def release(db, t: m.StockTransfer, role: str) -> m.SalesOrder:
    if t.status != "CREATED":
        raise BizError(f"{t.number} is already {t.status}")
    o = m.SalesOrder(warehouse_id=t.from_wh_id, number=next_number(db, t.from_wh_id, "SO", "SO"),
                     customer=f"{t.number} → {wh_code(db, t.to_wh_id)}", order_date=utcnow().date(), transfer_id=t.id)
    db.add(o)
    db.flush()
    for l in db.scalars(select(m.StockTransferLine).where(m.StockTransferLine.transfer_id == t.id)):
        db.add(m.SalesOrderLine(order_id=o.id, material_id=l.material_id, qty=l.qty))
    t.source_order_id, t.status = o.id, "RELEASED"
    log(db, t, f"Released — {o.number} at {wh_code(db, t.from_wh_id)}")
    return o


def pick_and_ship(db, t: m.StockTransfer, role: str):
    if t.status != "RELEASED":
        raise BizError(f"{t.number} must be released first")
    ctx = WhCtx(db, t.from_wh_id, role)
    o = db.get(m.SalesOrder, t.source_order_id)
    if o.status != "OPEN":
        raise BizError("Order is already waved — confirm the pick in the source warehouse")
    ctx.pick_and_ship(o)
    on_source_shipped(db, ctx, o, role)


def on_source_shipped(db, ctx: WhCtx, o: m.SalesOrder, role: str):
    t = db.get(m.StockTransfer, o.transfer_id)
    if not t or t.status != "RELEASED":
        return
    tasks = [x for d in db.scalars(select(m.WtDocument).where(m.WtDocument.wave_id == o.wave_id, m.WtDocument.type == "PICK"))
             for x in ctx.tasks_of(d.id) if x.status == "CONFIRMED"]
    if tasks and all(x.orders_ref == o.number for x in tasks):
        lines = [{"material_id": x.material_id, "qty": x.qty, "trk": x.tracking_no, "expiry": x.expiry} for x in tasks]
    else:  # wave shared with other orders → fall back to the ordered quantities
        lines = [{"material_id": l.material_id, "qty": l.qty, "trk": "", "expiry": None}
                 for l in db.scalars(select(m.SalesOrderLine).where(m.SalesOrderLine.order_id == o.id))]
    for l in lines:
        db.add(m.StockTransferShipped(transfer_id=t.id, leg=1, material_id=l["material_id"], qty=l["qty"],
                                      tracking_no=l["trk"] or "", expiry=l["expiry"]))
    log(db, t, f"Goods issued at {wh_code(db, t.from_wh_id)}")
    if t.via_wh_id:
        _create_asn(db, t.via_wh_id, t, lines, hub=True)
        t.status = "TO_HUB"
    else:
        _create_asn(db, t.to_wh_id, t, lines, hub=False)
        t.status = "IN_TRANSIT"


def _create_asn(db, wh_id: int, t: m.StockTransfer, lines: list[dict], hub: bool):
    a = m.Asn(warehouse_id=wh_id, number=next_number(db, wh_id, "ASN", "ASN"), vendor=f"{t.number} from {wh_code(db, t.from_wh_id)}",
              eta=utcnow().date(), transfer_id=t.id, hub_crossdock=hub)
    db.add(a)
    db.flush()
    for l in lines:
        if l["qty"] > 0:
            db.add(m.AsnLine(asn_id=a.id, material_id=l["material_id"], qty=l["qty"], tracking_no=l.get("trk") or "",
                             expiry=l.get("expiry")))
    if hub:
        t.hub_asn_id = a.id
    else:
        t.dest_asn_id = a.id
    log(db, t, f"{a.number} expected at {wh_code(db, wh_id)}")


def hub_receive(db, ctx: WhCtx, asn: m.Asn, role: str) -> m.CrossdockOrder:
    """A hub ASN never goes to putaway — it becomes a transport cross-dock order."""
    t = db.get(m.StockTransfer, asn.transfer_id) if asn.transfer_id else None
    lines = [{"material_id": l.material_id, "qty": l.qty, "trk": l.tracking_no, "expiry": l.expiry}
             for l in db.scalars(select(m.AsnLine).where(m.AsnLine.asn_id == asn.id))]
    xo = crossdock.create_order(ctx, "TCD", wh_code(db, t.from_wh_id) if t else asn.vendor,
                                wh_code(db, t.to_wh_id) if t else "Next warehouse", lines, transfer_id=t.id if t else None)
    crossdock.receive(ctx, xo)
    asn.status = "RECEIVED"
    if t:
        t.hub_xd_id, t.status = xo.id, "AT_HUB"
        log(db, t, f"Received at hub {ctx.wh.code} → cross-dock {xo.number}")
    return xo


def hub_receive_transfer(db, t: m.StockTransfer, role: str):
    if t.status != "TO_HUB":
        raise BizError(f"{t.number} is not on its way to the hub")
    ctx = WhCtx(db, t.via_wh_id, role)
    ctx.receive_asn(db.get(m.Asn, t.hub_asn_id))


def hub_confirm(db, t: m.StockTransfer, role: str):
    ctx = WhCtx(db, t.via_wh_id, role)
    crossdock.confirm_moves(ctx, db.get(m.CrossdockOrder, t.hub_xd_id))


def hub_dispatch(db, t: m.StockTransfer, role: str):
    ctx = WhCtx(db, t.via_wh_id, role)
    crossdock.goods_issue(ctx, db.get(m.CrossdockOrder, t.hub_xd_id))


def on_hub_dispatched(db, ctx: WhCtx, xo: m.CrossdockOrder, shipped: list[dict]):
    t = db.get(m.StockTransfer, xo.transfer_id)
    if not t:
        return
    for l in shipped:
        db.add(m.StockTransferShipped(transfer_id=t.id, leg=2, material_id=l["material_id"], qty=l["qty"],
                                      tracking_no=l["trk"] or "", expiry=l["expiry"]))
    log(db, t, f"Dispatched from hub {ctx.wh.code} ({xo.number})")
    _create_asn(db, t.to_wh_id, t, shipped, hub=False)
    t.status = "IN_TRANSIT"


def receive_dest(db, t: m.StockTransfer, role: str) -> dict:
    if t.status != "IN_TRANSIT":
        raise BizError(f"{t.number} is not in transit to the destination")
    ctx = WhCtx(db, t.to_wh_id, role)
    return ctx.receive_asn(db.get(m.Asn, t.dest_asn_id))


def on_dest_received(db, asn: m.Asn, doc):
    t = db.get(m.StockTransfer, asn.transfer_id)
    if t and t.dest_asn_id == asn.id and t.status == "IN_TRANSIT":
        t.status, t.done_at = "COMPLETED", utcnow()
        log(db, t, f"Received at {wh_code(db, t.to_wh_id)}" + (f" → {doc.number}" if doc else ""))
