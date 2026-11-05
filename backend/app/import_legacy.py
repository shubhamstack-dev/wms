"""Import data exported from the single-file HTML app (header → Export → wms-data-YYYY-MM-DD.json).

    python -m app.import_legacy path/to/wms-data.json            # into an empty database
    python -m app.import_legacy path/to/wms-data.json --reset    # drop + recreate tables first

Imports master data and open work: enterprise structure, warehouses (address + GSTIN), storage types, sections,
bin types, activity areas, queues, resource types, resources, work centers, doors, racks, bins, materials,
BOMs, stock (with batch / serial / expiry and FIFO order), open ASNs and open sales orders.
History (documents, waves, audit) stays in the export file.
"""
import json
import sys
from datetime import date
from sqlalchemy import select, func
from . import models as m
from .db import engine, SessionLocal
from .services.gst import check_gstin

ROLE = {"Available": "AVAILABLE", "Busy": "AVAILABLE", "Logged off": "LOGGED_OFF"}


def _d(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def import_data(db, G: dict) -> dict:
    if "whs" not in G:                                   # very old single-warehouse export
        G = {"whs": [G], "org": {}, "transfers": []}
    if db.scalar(select(func.count()).select_from(m.Warehouse)):
        raise SystemExit("Target database is not empty — use --reset or an empty database")
    warn, n = [], {"warehouses": 0, "bins": 0, "materials": 0, "stock": 0, "asns": 0, "orders": 0}
    org = G.get("org") or {}

    # enterprise
    cc_map, pl_map = {}, {}
    for c in org.get("companies", []):
        o = m.Company(code=c["code"][:10], name=c.get("name") or c["code"], legal_name=c.get("legalName", ""),
                      pan=(c.get("pan") or "").upper(), cin=c.get("cin", ""), currency=c.get("currency", "INR"), country=c.get("country", "IN"))
        db.add(o); db.flush(); cc_map[c["id"]] = o.id
    for p in org.get("plants", []):
        if p.get("companyId") not in cc_map:
            continue
        o = m.Plant(code=p["code"][:10], name=p.get("name") or p["code"], company_id=cc_map[p["companyId"]], city=p.get("city", ""))
        db.add(o); db.flush(); pl_map[p["id"]] = o.id

    # global materials: first warehouse defining a code wins
    mat_by_code = {}
    for w in G["whs"]:
        for it in w.get("items", []):
            if it["code"] in mat_by_code:
                continue
            o = m.Material(code=it["code"], name=it.get("name", ""), uom=it.get("uom", "EA")[:5], type=it.get("type", "FG"),
                           tracking=it.get("mgmt", "NONE"), weight=_num(it.get("weight")), volume=_num(it.get("volume")))
            db.add(o); db.flush(); mat_by_code[it["code"]] = o.id; n["materials"] += 1
    done_boms = set()
    for w in G["whs"]:
        code_of = {it["id"]: it["code"] for it in w.get("items", [])}
        for b in w.get("boms", []):
            pc = code_of.get(b["parent"])
            if not pc or pc in done_boms:
                continue
            bom = m.Bom(parent_material_id=mat_by_code[pc]); db.add(bom); db.flush(); done_boms.add(pc)
            for c in b.get("components", []):
                if code_of.get(c["item"]) in mat_by_code:
                    db.add(m.BomItem(bom_id=bom.id, material_id=mat_by_code[code_of[c["item"]]], qty=_num(c.get("qty"), 1)))

    wh_map = {}
    for w in G["whs"]:
        h = w.get("wh", {})
        a = h.get("addr") or {}
        g = check_gstin(h.get("gstin"))
        if h.get("gstin") and not g["ok"]:
            warn.append(f"{h.get('code')}: GSTIN {h.get('gstin')} dropped ({g['msg']})")
        W = m.Warehouse(code=(h.get("code") or "WH01")[:10], name=h.get("name") or "Warehouse", type=h.get("type", "DC"),
                        trade_name=h.get("tradeName", ""), addr_line1=a.get("line1", ""), addr_line2=a.get("line2", ""),
                        city=a.get("city") or h.get("city", ""), district=a.get("district", ""), state_code=a.get("state", ""),
                        pin=a.get("pin", ""), country=a.get("country") or "India", gstin=g.get("gstin", "") if g["ok"] else "",
                        contact=h.get("contact", ""), phone=h.get("phone", ""), email=h.get("email", ""))
        db.add(W); db.flush(); wh_map[w.get("id")] = W.id; n["warehouses"] += 1
        wid, ids = W.id, {}

        def add(kind, legacy_id, obj):
            db.add(obj); db.flush(); ids[(kind, legacy_id)] = obj.id
            return obj
        I = lambda kind, lid: ids.get((kind, lid)) if lid else None
        for z in w.get("zones", []):
            add("st", z["id"], m.StorageType(warehouse_id=wid, code=z["code"][:10], name=z.get("name", ""), role=z.get("type", "STORAGE"),
                                             putaway_rank=int(z.get("putawayRank") or 0), pick_rank=int(z.get("pickRank") or 0),
                                             mixed_storage=z.get("mixed") is not False))
        for s in w.get("sections", []):
            if I("st", s.get("stypeId")):
                add("sec", s["id"], m.StorageSection(warehouse_id=wid, storage_type_id=I("st", s["stypeId"]), code=s["code"][:10], name=s.get("name", "")))
        for t in w.get("binTypes", []):
            add("bt", t["id"], m.BinType(warehouse_id=wid, code=t["code"][:10], name=t.get("name", ""), max_qty=_num(t.get("maxQty")),
                                         max_weight=_num(t.get("maxWeight")), max_volume=_num(t.get("maxVol"))))
        for x in w.get("aareas", []):
            add("aa", x["id"], m.ActivityArea(warehouse_id=wid, code=x["code"][:10], name=x.get("name", ""), activity=x.get("activity", "ALL"),
                                              path_sort=x.get("sort", "serp")))
        for q in w.get("queues", []):
            add("q", q["id"], m.Queue(warehouse_id=wid, code=q["code"][:12], name=q.get("name", ""),
                                      activity_area_ids=[I("aa", i) for i in q.get("aareaIds", []) if I("aa", i)],
                                      task_types=[t for t in q.get("activities", []) if t in ("PICK", "PUTAWAY", "REPLEN", "REARR", "XDOCK")]))
        for t in w.get("resTypes", []):
            add("rt", t["id"], m.ResourceType(warehouse_id=wid, code=t["code"][:10], name=t.get("name", ""), max_level=int(t.get("maxLevel") or 0)))
        for r in w.get("resources", []):
            add("rs", r["id"], m.Resource(warehouse_id=wid, code=r["code"][:20], name=r.get("name", ""), resource_type_id=I("rt", r.get("typeId")),
                                          queue_ids=[I("q", i) for i in r.get("queueIds", []) if I("q", i)], status=ROLE.get(r.get("status"), "LOGGED_OFF")))
        for rk in w.get("racks", []):
            if not I("st", rk.get("stypeId")):
                continue
            add("rk", rk["id"], m.Rack(warehouse_id=wid, code=rk["code"][:20], name=rk.get("name", ""), storage_type_id=I("st", rk["stypeId"]),
                                       section_id=I("sec", rk.get("sectionId")), bin_type_id=I("bt", rk.get("binTypeId")),
                                       activity_area_id=I("aa", rk.get("aareaId")), pick_face=bool(rk.get("pickFace")),
                                       **{k: int(rk.get(src, d)) for k, src, d in (("x1", "x1", 0), ("y1", "y1", 0), ("x2", "x2", 0), ("y2", "y2", 0),
                                          ("aisle_from", "aFrom", 1), ("aisle_to", "aTo", 1), ("aisle_gap", "aGap", 1), ("pos_from", "pFrom", 1),
                                          ("pos_step", "pStep", 1), ("level_from", "lFrom", 1), ("level_to", "lTo", 1), ("pad", "pad", 2))},
                                       pattern=rk.get("pattern") or "{A}-{P}-{L}"))
        seen_pos = set()
        for b in w.get("bins", []):
            pos = (b.get("x", 0), b.get("y", 0), b.get("z", 1))
            if not I("st", b.get("zoneId")):
                warn.append(f"{W.code}: bin {b.get('code')} skipped (no storage type)"); continue
            if pos in seen_pos:
                warn.append(f"{W.code}: bin {b.get('code')} skipped (position {pos} already used)"); continue
            seen_pos.add(pos)
            add("bin", b["id"], m.Bin(warehouse_id=wid, code=b["code"][:40], storage_type_id=I("st", b["zoneId"]), section_id=I("sec", b.get("sectionId")),
                                      bin_type_id=I("bt", b.get("binTypeId")), activity_area_id=I("aa", b.get("aareaId")), rack_id=I("rk", b.get("rackId")),
                                      x=pos[0], y=pos[1], z=pos[2], max_qty=_num(b.get("maxQty")), max_weight=_num(b.get("maxWeight")),
                                      max_volume=_num(b.get("maxVol")), blocked=bool(b.get("blocked")), pick_face=bool(b.get("pickFace")),
                                      min_qty=_num(b.get("minQty")), replen_to=_num(b.get("replenTo")),
                                      fixed_material_id=mat_by_code.get(b.get("fixedItem") or "")))
            n["bins"] += 1
        for kind, rows, model in (("wc", w.get("wcs", []), m.WorkCenter), ("dr", w.get("doors", []), m.Door)):
            for x in rows:
                extra = {"kind": x.get("kind", "PACK")} if model is m.WorkCenter else {"direction": x.get("dir", "IN")}
                db.add(model(warehouse_id=wid, code=x["code"][:12], name=x.get("name", ""), bin_id=I("bin", x.get("binId")), **extra))
        code_of = {it["id"]: it["code"] for it in w.get("items", [])}
        for s in w.get("stock", []):
            if I("bin", s.get("binId")) and code_of.get(s.get("itemId")) in mat_by_code and _num(s.get("qty")) > 0:
                db.add(m.Stock(warehouse_id=wid, bin_id=I("bin", s["binId"]), material_id=mat_by_code[code_of[s["itemId"]]], qty=_num(s["qty"]),
                               batch=s.get("batch", ""), serial=s.get("serial", ""), expiry=_d(s.get("expiry")), gr_seq=int(s.get("seq") or 0)))
                n["stock"] += 1
        c = w.get("cfg") or {}
        db.add(m.WarehouseConfig(warehouse_id=wid, putaway_steps=int(c.get("putawaySteps") or 1), putaway_strategy=c.get("putawayStrategy", "nearest"),
                                 pick_steps=int(c.get("pickSteps") or 1), pick_strategy=c.get("pickStrategy", "FEFO"),
                                 stage_in_bin_id=I("bin", c.get("stageIn")), stage_out_bin_id=I("bin", c.get("stageOut")),
                                 explode_bom=c.get("explodeBom", True) is not False, xdock_opportunistic=bool(c.get("xdock")),
                                 xd_in_bin_id=I("bin", c.get("xdIn")), xd_out_bin_id=I("bin", c.get("xdOut")), wo_max_tasks=int(c.get("woMax") or 6)))
        hi = {"ASN": 0, "SO": 0}
        for a in w.get("asns", []):
            if a.get("status") != "Open":
                continue
            A = m.Asn(warehouse_id=wid, number=a["no"], vendor=a.get("vendor", ""), eta=_d(a.get("eta")))
            db.add(A); db.flush(); n["asns"] += 1
            for l in a.get("lines", []):
                if code_of.get(l.get("itemId")) in mat_by_code:
                    db.add(m.AsnLine(asn_id=A.id, material_id=mat_by_code[code_of[l["itemId"]]], qty=_num(l["qty"]), tracking_no=l.get("trk", ""), expiry=_d(l.get("expiry"))))
        for o in w.get("orders", []):
            if o.get("status") != "Open":
                continue
            O = m.SalesOrder(warehouse_id=wid, number=o["no"], customer=o.get("customer", ""), order_date=_d(o.get("date")))
            db.add(O); db.flush(); n["orders"] += 1
            for l in o.get("lines", []):
                if code_of.get(l.get("itemId")) in mat_by_code:
                    db.add(m.SalesOrderLine(order_id=O.id, material_id=mat_by_code[code_of[l["itemId"]]], qty=_num(l["qty"])))
        for key, prefix in (("asns", "ASN"), ("orders", "SO")):     # keep number ranges ahead of imported numbers
            for x in w.get(key, []):
                try:
                    hi[prefix] = max(hi[prefix], int(str(x.get("no", "")).split("-")[-1]))
                except ValueError:
                    pass
        for obj, last in (("ASN", hi["ASN"]), ("SO", hi["SO"])):
            if last:
                db.add(m.NumberRange(warehouse_id=wid, object=obj, last_no=last))
    for s in org.get("slocs", []):
        if s.get("plantId") in pl_map:
            db.add(m.StorageLocation(plant_id=pl_map[s["plantId"]], code=s["code"][:10], name=s.get("name", ""), warehouse_id=wh_map.get(s.get("whId"))))
    db.add(m.AuditLog(role="ADMIN", action="IMPORT", detail=f"Legacy import: {n}"))
    db.commit()
    return {"imported": n, "warnings": warn}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    if "--reset" in sys.argv:
        m.Base.metadata.drop_all(engine)
    m.Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print(json.dumps(import_data(db, data), indent=2))
