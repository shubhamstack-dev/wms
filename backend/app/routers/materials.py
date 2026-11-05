"""Global material master, BOMs, and stock views."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models as m, schemas as s
from ..core import get_role, require, to_dict, rows, audit, get_or_404, BizError

r = APIRouter(tags=["materials"])


@r.get("/materials")
def list_materials(wh: int | None = None, db: Session = Depends(get_db)):
    out = []
    for x in db.scalars(select(m.Material).order_by(m.Material.code)):
        d = to_dict(x)
        q = select(func.coalesce(func.sum(m.Stock.qty), 0)).where(m.Stock.material_id == x.id)
        d["stock"] = db.scalar(q.where(m.Stock.warehouse_id == wh) if wh else q)
        out.append(d)
    return out


@r.post("/materials")
def create_material(body: s.MaterialIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "master")
    if db.scalar(select(m.Material).where(m.Material.code == body.code)):
        raise BizError(f"Material {body.code} already exists")
    x = m.Material(**body.model_dump())
    db.add(x)
    db.flush()
    audit(db, None, role, "MASTER", f"Material {x.code} created")
    db.commit()
    return to_dict(x)


@r.put("/materials/{mid}")
def update_material(mid: int, body: s.MaterialIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "master")
    x = get_or_404(db, m.Material, mid)
    for k, v in body.model_dump().items():
        if k == "code" and v != x.code:
            raise BizError("Material code cannot be changed")
        setattr(x, k, v)
    audit(db, None, role, "MASTER", f"Material {x.code} updated")
    db.commit()
    return to_dict(x)


@r.delete("/materials/{mid}")
def delete_material(mid: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "master")
    x = get_or_404(db, m.Material, mid)
    if db.scalar(select(func.count()).select_from(m.Stock).where(m.Stock.material_id == mid)):
        raise BizError(f"{x.code} has stock in a warehouse")
    db.delete(x)
    db.commit()
    return {"ok": True}


@r.get("/boms")
def list_boms(db: Session = Depends(get_db)):
    return [{"parent_material_id": b.parent_material_id,
             "components": [{"material_id": i.material_id, "qty": i.qty}
                            for i in db.scalars(select(m.BomItem).where(m.BomItem.bom_id == b.id))]}
            for b in db.scalars(select(m.Bom))]


@r.put("/boms/{parent_id}")
def set_bom(parent_id: int, body: s.BomIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "master")
    get_or_404(db, m.Material, parent_id)
    if any(c.material_id == parent_id for c in body.components):
        raise BizError("A material cannot be its own component")
    b = db.scalar(select(m.Bom).where(m.Bom.parent_material_id == parent_id))
    if not body.components:
        if b:
            db.delete(b)
        db.commit()
        return {"ok": True}
    if b is None:
        b = m.Bom(parent_material_id=parent_id)
        db.add(b)
        db.flush()
    db.execute(delete(m.BomItem).where(m.BomItem.bom_id == b.id))
    for c in body.components:
        get_or_404(db, m.Material, c.material_id)
        db.add(m.BomItem(bom_id=b.id, material_id=c.material_id, qty=c.qty))
    audit(db, None, role, "MASTER", f"BOM of material {parent_id} saved ({len(body.components)} components)")
    db.commit()
    return {"ok": True}


@r.get("/warehouses/{wh}/stock")
def stock(wh: int, db: Session = Depends(get_db)):
    q = (select(m.Stock, m.Bin.code, m.Material.code, m.Material.name, m.Material.uom)
         .join(m.Bin, m.Bin.id == m.Stock.bin_id).join(m.Material, m.Material.id == m.Stock.material_id)
         .where(m.Stock.warehouse_id == wh).order_by(m.Bin.code))
    return [{**to_dict(st), "bin_code": bc, "material_code": mc, "material_name": mn, "uom": u} for st, bc, mc, mn, u in db.execute(q)]


@r.get("/stock-overview")
def stock_overview(db: Session = Depends(get_db)):
    """Material × warehouse availability (enterprise view)."""
    data = {}
    for mid, wh, q in db.execute(select(m.Stock.material_id, m.Stock.warehouse_id, func.sum(m.Stock.qty))
                                  .group_by(m.Stock.material_id, m.Stock.warehouse_id)):
        data.setdefault(mid, {})[wh] = q
    transit = {}
    # only goods on the road — at the hub they are already part of the hub's stock
    for t in db.scalars(select(m.StockTransfer).where(m.StockTransfer.status.in_(["TO_HUB", "IN_TRANSIT"]))):
        leg = 2 if t.status == "IN_TRANSIT" and t.via_wh_id else 1
        for l in db.scalars(select(m.StockTransferShipped).where(m.StockTransferShipped.transfer_id == t.id,
                                                                  m.StockTransferShipped.leg == leg)):
            transit[l.material_id] = transit.get(l.material_id, 0) + l.qty
    return [{"material_id": x.id, "code": x.code, "name": x.name, "by_warehouse": data.get(x.id, {}),
             "in_transit": transit.get(x.id, 0)} for x in db.scalars(select(m.Material).order_by(m.Material.code))]
