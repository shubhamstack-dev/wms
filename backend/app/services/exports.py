"""GST / address master data for other systems (ERP, e-way bill, transport). Capture only — no billing."""
import csv, io
from datetime import datetime
from sqlalchemy import select
from .. import models as m
from .gst import check_gstin, GST_STATES
from ..core import utcnow


def company_of(db, wh_id):
    sl = db.scalars(select(m.StorageLocation).where(m.StorageLocation.warehouse_id == wh_id)).first()
    pl = db.get(m.Plant, sl.plant_id) if sl else None
    return db.get(m.Company, pl.company_id) if pl else None


def issues(db, w: m.Warehouse) -> list[str]:
    out, g, c = [], check_gstin(w.gstin), company_of(db, w.id)
    if not (w.addr_line1 and w.city and w.state_code and w.pin):
        out.append("Address incomplete")
    if not g["ok"]:
        out.append(g["msg"])
    else:
        if w.state_code and g["state"] != w.state_code:
            out.append(f"GSTIN state {g['state']} ≠ address state {w.state_code}")
        if c and c.pan and g["pan"] != c.pan.upper():
            out.append("GSTIN PAN ≠ company PAN")
    if not c:
        out.append("Not linked to a company code (assign a storage location)")
    return out


def master_rows(db) -> list[dict]:
    out = []
    for w in db.scalars(select(m.Warehouse).order_by(m.Warehouse.code)):
        g, c = check_gstin(w.gstin), company_of(db, w.id)
        sls = [{"plant": db.get(m.Plant, s.plant_id).code, "sloc": s.code}
               for s in db.scalars(select(m.StorageLocation).where(m.StorageLocation.warehouse_id == w.id))]
        st = g["state"] if g["ok"] else w.state_code
        out.append({"warehouse": w.code, "name": w.name, "type": w.type, "tradeName": w.trade_name,
                    "companyCode": c.code if c else "", "companyLegalName": c.legal_name if c else "",
                    "companyPan": c.pan if c else "", "companyCin": c.cin if c else "", "plantStorageLocations": sls,
                    "gstin": w.gstin, "gstinValid": g["ok"], "gstStateCode": st, "gstStateName": GST_STATES.get(st, ""),
                    "pan": g.get("pan", ""),
                    "address": {"line1": w.addr_line1, "line2": w.addr_line2, "city": w.city, "district": w.district,
                                "stateCode": w.state_code, "state": GST_STATES.get(w.state_code, ""), "pin": w.pin,
                                "country": w.country},
                    "contact": {"person": w.contact, "phone": w.phone, "email": w.email}, "issues": issues(db, w)})
    return out


def master_json(db):
    return {"exportedAt": utcnow().isoformat() + "Z", "source": "WMS", "type": "WAREHOUSE_GST_MASTER",
            "warehouses": master_rows(db)}


def master_csv(db) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["warehouse", "name", "type", "companyCode", "companyLegalName", "companyPan", "plant/sloc", "gstin",
                 "gstinValid", "gstStateCode", "gstStateName", "address1", "address2", "city", "district", "pin", "country",
                 "contactPerson", "phone", "email"])
    for r in master_rows(db):
        a = r["address"]
        wr.writerow([r["warehouse"], r["name"], r["type"], r["companyCode"], r["companyLegalName"], r["companyPan"],
                     " ".join(f"{x['plant']}/{x['sloc']}" for x in r["plantStorageLocations"]), r["gstin"], r["gstinValid"],
                     r["gstStateCode"], r["gstStateName"], a["line1"], a["line2"], a["city"], a["district"], a["pin"],
                     a["country"], r["contact"]["person"], r["contact"]["phone"], r["contact"]["email"]])
    return buf.getvalue()


def transfers_json(db):
    by = {r["warehouse"]: r for r in master_rows(db)}
    mats = {x.id: x.code for x in db.scalars(select(m.Material))}

    def party(wid):
        if not wid:
            return None
        r = by.get(db.get(m.Warehouse, wid).code)
        return {"warehouse": r["warehouse"], "name": r["name"], "gstin": r["gstin"], "gstStateCode": r["gstStateCode"],
                "address": r["address"]}
    out = []
    for t in db.scalars(select(m.StockTransfer).order_by(m.StockTransfer.id)):
        shipped = list(db.scalars(select(m.StockTransferShipped).where(m.StockTransferShipped.transfer_id == t.id,
                                                                        m.StockTransferShipped.leg == 1)))
        src = shipped or list(db.scalars(select(m.StockTransferLine).where(m.StockTransferLine.transfer_id == t.id)))
        merged = {}
        for l in src:
            k = (mats[l.material_id], getattr(l, "tracking_no", ""))
            merged[k] = merged.get(k, 0) + l.qty
        f, to = db.get(m.Warehouse, t.from_wh_id), db.get(m.Warehouse, t.to_wh_id)
        out.append({"transfer": t.number, "status": t.status, "created": t.created_at.isoformat() if t.created_at else "",
                    "completed": t.done_at.isoformat() if t.done_at else "", "from": party(t.from_wh_id),
                    "via": party(t.via_wh_id), "to": party(t.to_wh_id),
                    "sameGstin": bool(f.gstin and f.gstin == to.gstin),
                    "lines": [{"material": k[0], "qty": q, "batchOrSerial": k[1]} for k, q in merged.items()]})
    return {"exportedAt": utcnow().isoformat() + "Z", "source": "WMS", "type": "STOCK_TRANSFER_MOVEMENTS",
            "transfers": out}
