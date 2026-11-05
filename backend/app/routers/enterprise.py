"""Enterprise structure: company codes, plants, storage locations, warehouses; GST validation & export."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models as m, schemas as s
from ..core import get_role, require, to_dict, rows, audit, get_or_404, ROLES, BizError
from ..services.gst import check_gstin, GST_STATES
from ..services import exports

r = APIRouter(tags=["enterprise"])


@r.get("/meta")
def meta():
    return {"gst_states": GST_STATES, "roles": {k: sorted(v) for k, v in ROLES.items()}}


@r.get("/gst/validate")
def gst_validate(gstin: str):
    return check_gstin(gstin)


def _simple(model, In, path, scope=None):
    @r.get(f"/{path}", name=f"list_{path}")
    def _list(db: Session = Depends(get_db)):
        return rows(db.scalars(select(model).order_by(model.code)))

    @r.post(f"/{path}", name=f"create_{path}")
    def _create(body: In, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, "setup")
        o = model(**body.model_dump())
        db.add(o)
        db.flush()
        audit(db, None, role, "ENTERPRISE", f"{path} {o.code} created")
        db.commit()
        return to_dict(o)

    @r.put(f"/{path}/{{id_}}", name=f"update_{path}")
    def _update(id_: int, body: In, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, "setup")
        o = get_or_404(db, model, id_)
        for k, v in body.model_dump().items():
            setattr(o, k, v)
        audit(db, None, role, "ENTERPRISE", f"{path} {o.code} updated")
        db.commit()
        return to_dict(o)

    @r.delete(f"/{path}/{{id_}}", name=f"delete_{path}")
    def _delete(id_: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
        require(role, "setup")
        o = get_or_404(db, model, id_)
        db.delete(o)
        audit(db, None, role, "ENTERPRISE", f"{path} {o.code} deleted")
        db.commit()
        return {"ok": True}


_simple(m.Company, s.CompanyIn, "companies")
_simple(m.Plant, s.PlantIn, "plants")
_simple(m.StorageLocation, s.StorageLocationIn, "storage-locations")


def _wh_out(db, w: m.Warehouse) -> dict:
    d = to_dict(w)
    W = lambda model, *c: db.scalar(select(func.count()).select_from(model).where(model.warehouse_id == w.id, *c)) or 0
    d.update({
        "bins": W(m.Bin), "storage_types": W(m.StorageType),
        "units": db.scalar(select(func.coalesce(func.sum(m.Stock.qty), 0)).where(m.Stock.warehouse_id == w.id)),
        "open_docs": W(m.WtDocument, m.WtDocument.status != "DONE"), "open_asns": W(m.Asn, m.Asn.status == "OPEN"),
        "open_xd": W(m.CrossdockOrder, m.CrossdockOrder.status != "SHIPPED"),
        "inbound_transfers": db.scalar(select(func.count()).select_from(m.StockTransfer).where(
            m.StockTransfer.status != "COMPLETED", (m.StockTransfer.to_wh_id == w.id) | (m.StockTransfer.via_wh_id == w.id))),
        "outbound_transfers": db.scalar(select(func.count()).select_from(m.StockTransfer).where(
            m.StockTransfer.from_wh_id == w.id, m.StockTransfer.status.in_(["CREATED", "RELEASED"]))),
        "gstin_valid": check_gstin(w.gstin)["ok"], "issues": exports.issues(db, w),
        "storage_locations": [f"{db.get(m.Plant, x.plant_id).code}/{x.code}" for x in
                              db.scalars(select(m.StorageLocation).where(m.StorageLocation.warehouse_id == w.id))],
    })
    return d


@r.get("/warehouses")
def list_warehouses(db: Session = Depends(get_db)):
    return [_wh_out(db, w) for w in db.scalars(select(m.Warehouse).order_by(m.Warehouse.code))]


@r.get("/warehouses/{wh}")
def get_warehouse(wh: int, db: Session = Depends(get_db)):
    return _wh_out(db, get_or_404(db, m.Warehouse, wh))


WH_FIELDS = set(s.WarehouseIn.model_fields)


def _copy_structure(db, src: int, dst: int, with_bins: bool):
    idmap = {}

    def clone(model, extra=None, keyname=None):
        for o in list(db.scalars(select(model).where(model.warehouse_id == src))):
            d = {c.name: getattr(o, c.name) for c in model.__table__.columns if c.name not in ("id", "warehouse_id")}
            d.update(extra(d) if extra else {})
            n = model(warehouse_id=dst, **d)
            db.add(n)
            db.flush()
            idmap[(model.__name__, o.id)] = n.id
    M = lambda name, i: idmap.get((name, i)) if i else None
    clone(m.StorageType)
    clone(m.StorageSection, lambda d: {"storage_type_id": M("StorageType", d["storage_type_id"])})
    clone(m.BinType)
    clone(m.ActivityArea)
    clone(m.Queue, lambda d: {"activity_area_ids": [M("ActivityArea", x) for x in d["activity_area_ids"] or [] if M("ActivityArea", x)]})
    clone(m.ResourceType)
    if with_bins:
        common = lambda d: {"storage_type_id": M("StorageType", d["storage_type_id"]), "section_id": M("StorageSection", d["section_id"]),
                            "bin_type_id": M("BinType", d["bin_type_id"]), "activity_area_id": M("ActivityArea", d["activity_area_id"])}
        clone(m.Rack, common)
        clone(m.Bin, lambda d: {**common(d), "rack_id": M("Rack", d["rack_id"]), "blocked": False})
    cfg = db.get(m.WarehouseConfig, src)
    if cfg:
        d = {c.name: getattr(cfg, c.name) for c in cfg.__table__.columns if c.name != "warehouse_id"}
        for k in ("stage_in_bin_id", "stage_out_bin_id", "xd_in_bin_id", "xd_out_bin_id"):
            d[k] = M("Bin", d[k])
        db.add(m.WarehouseConfig(warehouse_id=dst, **d))


@r.post("/warehouses")
def create_warehouse(body: s.WarehouseCreate, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    if db.scalar(select(m.Warehouse).where(m.Warehouse.code == body.code)):
        raise BizError(f"Warehouse number {body.code} already exists")
    w = m.Warehouse(**{k: v for k, v in body.model_dump().items() if k in WH_FIELDS})
    db.add(w)
    db.flush()
    if body.copy_from_id:
        _copy_structure(db, body.copy_from_id, w.id, body.copy_bins)
    else:
        db.add(m.WarehouseConfig(warehouse_id=w.id))
    if body.plant_id and body.sloc_code:
        sl = db.scalar(select(m.StorageLocation).where(m.StorageLocation.plant_id == body.plant_id,
                                                       m.StorageLocation.code == body.sloc_code.upper()))
        if sl:
            sl.warehouse_id = w.id
        else:
            db.add(m.StorageLocation(plant_id=body.plant_id, code=body.sloc_code.upper(), name=w.name, warehouse_id=w.id))
    audit(db, w.id, role, "ENTERPRISE", f"Warehouse {w.code} created")
    db.commit()
    return _wh_out(db, w)


@r.put("/warehouses/{wh}")
def update_warehouse(wh: int, body: s.WarehouseIn, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    w = get_or_404(db, m.Warehouse, wh)
    if db.scalar(select(m.Warehouse).where(m.Warehouse.code == body.code, m.Warehouse.id != wh)):
        raise BizError(f"Warehouse number {body.code} already exists")
    for k, v in body.model_dump().items():
        setattr(w, k, v)
    audit(db, wh, role, "ENTERPRISE", f"Warehouse {w.code} master data updated" + (f" · GSTIN {w.gstin}" if w.gstin else ""))
    db.commit()
    return _wh_out(db, w)


@r.delete("/warehouses/{wh}")
def delete_warehouse(wh: int, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require(role, "setup")
    w = get_or_404(db, m.Warehouse, wh)
    if db.scalar(select(func.count()).select_from(m.Stock).where(m.Stock.warehouse_id == wh)):
        raise BizError(f"{w.code} still holds stock")
    if db.scalar(select(func.count()).select_from(m.StockTransfer).where(
            m.StockTransfer.status != "COMPLETED",
            (m.StockTransfer.from_wh_id == wh) | (m.StockTransfer.via_wh_id == wh) | (m.StockTransfer.to_wh_id == wh))):
        raise BizError("Open transfers involve this warehouse")
    if db.scalar(select(func.count()).select_from(m.Warehouse)) <= 1:
        raise BizError("At least one warehouse is required")
    for sl in db.scalars(select(m.StorageLocation).where(m.StorageLocation.warehouse_id == wh)):
        sl.warehouse_id = None
    db.delete(w)
    audit(db, None, role, "ENTERPRISE", f"Warehouse {w.code} deleted")
    db.commit()
    return {"ok": True}


@r.get("/exports/gst-master.json")
def export_json(db: Session = Depends(get_db)):
    return exports.master_json(db)


@r.get("/exports/gst-master.csv", response_class=PlainTextResponse)
def export_csv(db: Session = Depends(get_db)):
    return PlainTextResponse(exports.master_csv(db), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=warehouse-gst-master.csv"})


@r.get("/exports/transfers.json")
def export_transfers(db: Session = Depends(get_db)):
    return exports.transfers_json(db)
