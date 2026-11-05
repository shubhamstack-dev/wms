"""Bins, the graphical layout designer, and racks (start → end bin generation)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models as m, schemas as s
from ..core import get_role, require, to_dict, rows, get_or_404
from ..services.engine import WhCtx
from ..services import racks

r = APIRouter(prefix="/warehouses/{wh}", tags=["layout"])


@r.get("/bins")
def list_bins(wh: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    out = []
    for b in sorted(ctx.bins.values(), key=lambda b: (b.z, b.y, b.x)):
        d = to_dict(b)
        d.update(qty=ctx.bin_qty(b.id), fill=round(ctx.fill_pct(b), 3), role=ctx.role_of(b))
        out.append(d)
    db.commit()
    return out


@r.get("/bins/{bin_id}")
def get_bin(wh: int, bin_id: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    b = get_or_404(db, m.Bin, bin_id, wh)
    d = to_dict(b)
    d["contents"] = [{**to_dict(x), "material_code": ctx.mats[x.material_id].code, "material_name": ctx.mats[x.material_id].name}
                     for x in ctx.bin_rows(b.id)]
    d.update(qty=ctx.bin_qty(b.id), fill=round(ctx.fill_pct(b), 3), role=ctx.role_of(b))
    return d


@r.patch("/bins/{bin_id}")
def patch_bin(wh: int, bin_id: int, body: s.BinPatch, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    b = get_or_404(db, m.Bin, bin_id, wh)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    WhCtx(db, wh, role).log("SETUP", f"Bin {b.code} updated")
    db.commit()
    return to_dict(b)


@r.post("/designer/draw")
def draw(wh: int, body: s.DrawIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    res = racks.draw_bins(WhCtx(db, wh, role), body.model_dump())
    db.commit()
    return res


@r.post("/designer/assign")
def assign(wh: int, body: s.BulkAssignIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    res = racks.bulk_assign(WhCtx(db, wh, role), body.model_dump())
    db.commit()
    return res


@r.post("/designer/delete")
def delete_bins(wh: int, body: s.IdsIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    ctx = WhCtx(db, wh, role)
    res = racks.delete_empty_bins(ctx, [ctx.bins[i] for i in body.ids if i in ctx.bins])
    ctx.log("ORG", f"Designer: {res['deleted']} bins deleted")
    db.commit()
    return res


@r.get("/racks")
def list_racks(wh: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    out = []
    for rk in db.scalars(select(m.Rack).where(m.Rack.warehouse_id == wh).order_by(m.Rack.code)):
        p = racks.plan(ctx, to_dict(rk))
        d = to_dict(rk)
        d.update(planned=len(p["items"]), generated=sum(1 for b in ctx.bins.values() if b.rack_id == rk.id),
                 new=p["counts"].get("new", 0), first_code=p["items"][0]["code"] if p["items"] else "",
                 last_code=p["items"][-1]["code"] if p["items"] else "", horizontal=p["horizontal"], positions=p["positions"])
        out.append(d)
    return out


@r.post("/racks/preview")
def preview(wh: int, body: s.RackIn, db: Session = Depends(get_db)):
    return racks.plan(WhCtx(db, wh), body.model_dump())


@r.post("/racks")
def create_rack(wh: int, body: s.RackIn, generate: bool = False, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    ctx = WhCtx(db, wh, role)
    get_or_404(db, m.StorageType, body.storage_type_id, wh)
    rk = m.Rack(warehouse_id=wh, **body.model_dump())
    db.add(rk)
    db.flush()
    res = racks.generate(ctx, rk) if generate else {}
    ctx.log("ORG", f"Rack {rk.code} saved")
    db.commit()
    return {**to_dict(rk), **res}


@r.put("/racks/{rack_id}")
def update_rack(wh: int, rack_id: int, body: s.RackIn, generate: bool = False, db: Session = Depends(get_db),
                role: str = Depends(get_role)):
    require(role, "setup")
    ctx = WhCtx(db, wh, role)
    rk = get_or_404(db, m.Rack, rack_id, wh)
    for k, v in body.model_dump().items():
        setattr(rk, k, v)
    db.flush()
    res = racks.generate(ctx, rk) if generate else {}
    db.commit()
    return {**to_dict(rk), **res}


@r.post("/racks/{rack_id}/generate")
def generate(wh: int, rack_id: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    ctx = WhCtx(db, wh, role)
    res = racks.generate(ctx, get_or_404(db, m.Rack, rack_id, wh))
    db.commit()
    return res


@r.post("/racks/{rack_id}/delete-bins")
def rack_delete_bins(wh: int, rack_id: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    ctx = WhCtx(db, wh, role)
    rk = get_or_404(db, m.Rack, rack_id, wh)
    res = racks.delete_empty_bins(ctx, [b for b in ctx.bins.values() if b.rack_id == rk.id])
    ctx.log("ORG", f"Rack {rk.code}: {res['deleted']} empty bins deleted")
    db.commit()
    return res


@r.delete("/racks/{rack_id}")
def delete_rack(wh: int, rack_id: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    """Deletes the definition only; generated bins stay."""
    require(role, "setup")
    rk = get_or_404(db, m.Rack, rack_id, wh)
    for b in db.scalars(select(m.Bin).where(m.Bin.rack_id == rk.id)):
        b.rack_id = None
    db.delete(rk)
    db.commit()
    return {"ok": True}
