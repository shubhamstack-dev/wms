"""Warehouse organisation units (generic CRUD) and strategy configuration."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models as m, schemas as s
from ..core import get_role, require, to_dict, rows, audit, get_or_404, BizError
from ..services.engine import WhCtx

r = APIRouter(prefix="/warehouses/{wh}", tags=["organisation"])


def _check_refs(db, wh, body):
    d = body.model_dump()
    refs = {"storage_type_id": m.StorageType, "resource_type_id": m.ResourceType, "bin_id": m.Bin}
    for k, model in refs.items():
        if d.get(k):
            get_or_404(db, model, d[k], wh)
    for k, model in (("activity_area_ids", m.ActivityArea), ("queue_ids", m.Queue)):
        for i in d.get(k) or []:
            get_or_404(db, model, i, wh)


def _apply_bin_type(db, wh, bt):
    for b in db.scalars(select(m.Bin).where(m.Bin.warehouse_id == wh, m.Bin.bin_type_id == bt.id)):
        if bt.max_qty > 0: b.max_qty = bt.max_qty
        if bt.max_weight > 0: b.max_weight = bt.max_weight
        if bt.max_volume > 0: b.max_volume = bt.max_volume


def _guard_storage_type(db, wh, o):
    if db.scalar(select(func.count()).select_from(m.Bin).where(m.Bin.storage_type_id == o.id)):
        raise BizError(f"Storage type {o.code} still has bins — move or delete them first")


def _guard_resource_type(db, wh, o):
    if db.scalar(select(func.count()).select_from(m.Resource).where(m.Resource.resource_type_id == o.id)):
        raise BizError(f"Resource type {o.code} is used by resources")


UNITS = {
    "storage-types": (m.StorageType, s.StorageTypeIn, None, _guard_storage_type),
    "sections": (m.StorageSection, s.SectionIn, None, None),
    "bin-types": (m.BinType, s.BinTypeIn, _apply_bin_type, None),
    "activity-areas": (m.ActivityArea, s.ActivityAreaIn, None, None),
    "queues": (m.Queue, s.QueueIn, None, None),
    "resource-types": (m.ResourceType, s.ResourceTypeIn, None, _guard_resource_type),
    "resources": (m.Resource, s.ResourceIn, None, None),
    "work-centers": (m.WorkCenter, s.WorkCenterIn, None, None),
    "doors": (m.Door, s.DoorIn, None, None),
}


def _register(path, model, In, after_save, guard_delete):
    @r.get(f"/{path}", name=f"list_{path}")
    def _list(wh: int, db: Session = Depends(get_db)):
        return rows(db.scalars(select(model).where(model.warehouse_id == wh).order_by(model.code)))

    @r.post(f"/{path}", name=f"create_{path}")
    def _create(wh: int, body: In, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, "setup")
        get_or_404(db, m.Warehouse, wh)
        _check_refs(db, wh, body)
        o = model(warehouse_id=wh, **body.model_dump())
        db.add(o)
        db.flush()
        after_save and after_save(db, wh, o)
        audit(db, wh, role, "ORG", f"{path} {o.code} created")
        db.commit()
        return to_dict(o)

    @r.put(f"/{path}/{{id_}}", name=f"update_{path}")
    def _update(wh: int, id_: int, body: In, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, "setup")
        o = get_or_404(db, model, id_, wh)
        _check_refs(db, wh, body)
        for k, v in body.model_dump().items():
            setattr(o, k, v)
        db.flush()
        after_save and after_save(db, wh, o)
        audit(db, wh, role, "ORG", f"{path} {o.code} updated")
        db.commit()
        return to_dict(o)

    @r.delete(f"/{path}/{{id_}}", name=f"delete_{path}")
    def _delete(wh: int, id_: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, "setup")
        o = get_or_404(db, model, id_, wh)
        guard_delete and guard_delete(db, wh, o)
        db.delete(o)
        audit(db, wh, role, "ORG", f"{path} {o.code} deleted")
        db.commit()
        return {"ok": True}


for _p, (_m, _i, _a, _g) in UNITS.items():
    _register(_p, _m, _i, _a, _g)


@r.get("/config")
def get_config(wh: int, db: Session = Depends(get_db)):
    ctx = WhCtx(db, wh)
    db.commit()
    return to_dict(ctx.cfg)


@r.put("/config")
def put_config(wh: int, body: s.ConfigIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "config")
    ctx = WhCtx(db, wh, role)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k.endswith("_bin_id") and v:
            get_or_404(db, m.Bin, v, wh)
        setattr(ctx.cfg, k, v)
    ctx.log("CONFIG", "Strategies updated: " + ", ".join(f"{k}={v}" for k, v in body.model_dump(exclude_unset=True).items()))
    db.commit()
    return to_dict(ctx.cfg)
