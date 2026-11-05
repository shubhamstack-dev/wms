"""Demo data: 1 company, 2 plants, 3 warehouses (WH01 Bengaluru DC, WH02 Chennai DC, XD01 Hosur cross-dock hub).

    python -m app.seed            # create tables if missing, load demo data (refuses if data exists)
    python -m app.seed --reset    # DROP all WMS tables, recreate, load demo data
"""
import sys
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from . import models as m
from .db import engine, SessionLocal
from .core import next_number
from .services.engine import WhCtx
from .services.gst import make_gstin
from .services import racks

PAN = "AABCB1234F"


def _add(db, obj):
    db.add(obj)
    db.flush()
    return obj


def _wh(db, code, name, type_, city, district, state, pin, line1, line2, contact, phone):
    w = _add(db, m.Warehouse(code=code, name=name, type=type_, city=city, district=district, state_code=state, pin=pin,
                             addr_line1=line1, addr_line2=line2, gstin=make_gstin(state, PAN), contact=contact, phone=phone,
                             email=f"{code.lower()}@bharatpumps.example"))
    _add(db, m.WarehouseConfig(warehouse_id=w.id))
    return w


def _st(db, wh, code, name, role, pa, pk, mixed=True):
    return _add(db, m.StorageType(warehouse_id=wh.id, code=code, name=name, role=role, putaway_rank=pa, pick_rank=pk, mixed_storage=mixed))


def _bin(db, wh, code, st, x, y, z=1, bt=None, aa=None, sec=None, pick_face=False, fixed=None):
    return _add(db, m.Bin(warehouse_id=wh.id, code=code, storage_type_id=st.id, x=x, y=y, z=z,
                          bin_type_id=bt.id if bt else None, activity_area_id=aa.id if aa else None,
                          section_id=sec.id if sec else None, max_qty=bt.max_qty if bt else 100,
                          max_weight=bt.max_weight if bt else 0, max_volume=bt.max_volume if bt else 0,
                          pick_face=pick_face, min_qty=25 if pick_face else 0, replen_to=120 if pick_face else 0,
                          fixed_material_id=fixed.id if fixed else None))


def seed(db: Session):
    if db.scalar(select(func.count()).select_from(m.Warehouse)):
        raise SystemExit("Database already has data — use --reset to replace it")
    cc = _add(db, m.Company(code="1000", name="Bharat Pumps Ltd", legal_name="Bharat Pumps Limited", pan=PAN,
                            cin="U29120KA2010PLC054321"))
    p1 = _add(db, m.Plant(code="1000", name="Bengaluru plant", company_id=cc.id, city="Bengaluru"))
    p2 = _add(db, m.Plant(code="2000", name="Chennai plant", company_id=cc.id, city="Chennai"))

    M = lambda code, name, typ, trk, w, v: _add(db, m.Material(code=code, name=name, type=typ, tracking=trk, weight=w, volume=v))
    fg, sf = M("FG-100", "Assembled Pump Unit", "FG", "SERIAL", 18, 0.09), M("SF-200", "Motor Sub-assembly", "SFG", "BATCH", 9, 0.04)
    rm1, rm2 = M("RM-301", "Steel Housing", "RM", "NONE", 6, 0.03), M("RM-302", "Bearing Set", "RM", "BATCH", 0.4, 0.002)
    rm3, pk = M("RM-303", "Impeller", "RM", "NONE", 1.2, 0.006), M("PK-401", "Export Carton", "PACK", "NONE", 0.6, 0.05)
    b1, b2 = _add(db, m.Bom(parent_material_id=fg.id)), _add(db, m.Bom(parent_material_id=sf.id))
    for bom, mat, q in ((b1, sf, 1), (b1, rm1, 1), (b1, rm3, 2), (b1, pk, 1), (b2, rm2, 4)):
        db.add(m.BomItem(bom_id=bom.id, material_id=mat.id, qty=q))

    # ── WH01 Bengaluru DC ──
    w1 = _wh(db, "WH01", "Central Distribution Centre", "DC", "Bengaluru", "Bengaluru Urban", "29", "560099",
             "Plot 42, KIADB Industrial Area", "Bommasandra, Hosur Road", "Rakesh Rao", "+91 80 4000 1100")
    rcv, pck = _st(db, w1, "RCV", "Receiving dock", "RECEIVING", 0, 9), _st(db, w1, "PCK", "Pick face aisle", "STORAGE", 1, 0, False)
    za, blk = _st(db, w1, "ZA", "Rack zone A", "STORAGE", 2, 1), _st(db, w1, "BLK", "Bulk floor", "STORAGE", 3, 2)
    shp = _st(db, w1, "SHP", "Shipping staging", "SHIPPING", 9, 0)
    SC = lambda st, c, n: _add(db, m.StorageSection(warehouse_id=w1.id, storage_type_id=st.id, code=c, name=n))
    sp, sa1, sa2, sb = SC(pck, "S01", "Fast movers"), SC(za, "S01", "Ground level (golden zone)"), SC(za, "S02", "Upper levels"), SC(blk, "S01", "Floor blocks")
    BT = lambda c, n, q, w, v: _add(db, m.BinType(warehouse_id=w1.id, code=c, name=n, max_qty=q, max_weight=w, max_volume=v))
    bpf, brk, bfl, bdk = BT("PF", "Shelf pick face", 120, 250, 1.2), BT("RK", "Pallet rack slot", 80, 600, 2.5), \
        BT("FL", "Floor block", 600, 4000, 20), BT("DK", "Dock door / staging lane", 2000, 9000, 60)
    AA = lambda c, n, srt: _add(db, m.ActivityArea(warehouse_id=w1.id, code=c, name=n, path_sort=srt))
    aap, aab, aad = AA("PICK", "Pick faces + rack", "serp"), AA("BULK", "Bulk floor", "aisle"), AA("DOCK", "Docks & staging", "aisle")
    faces = [_bin(db, w1, f"P-01-{i + 1:02d}", pck, i, 0, bt=bpf, aa=aap, sec=sp, pick_face=True,
                  fixed=[rm1, rm2, rm3][i] if i < 3 else None) for i in range(6)]
    ctx = WhCtx(db, w1.id, "ADMIN")
    rack_a = _add(db, m.Rack(warehouse_id=w1.id, code="RACK-A", name="Selective pallet rack, aisles 1–2", storage_type_id=za.id,
                             bin_type_id=brk.id, activity_area_id=aap.id, x1=0, y1=2, x2=3, y2=2, aisle_from=1, aisle_to=2,
                             level_from=1, level_to=3, pattern="A{A}-R{P}-L{L}"))
    racks.generate(ctx, rack_a)
    for b in ctx.bins.values():
        if b.rack_id == rack_a.id:
            b.section_id = sa1.id if b.z == 1 else sa2.id
    bulk = [_bin(db, w1, f"BLK-{i + 1:03d}", blk, i, 5, bt=bfl, aa=aab, sec=sb) for i in range(6)]
    d_in = [_bin(db, w1, f"D-01-P{i + 1:02d}", rcv, 8 + i, 0, bt=bdk, aa=aad) for i in range(2)]
    d_out = [_bin(db, w1, f"D-02-P{i + 1:02d}", shp, 8 + i, 5, bt=bdk, aa=aad) for i in range(2)]
    for i, b in enumerate(d_in + d_out):
        db.add(m.Door(warehouse_id=w1.id, code=f"DOOR-{i + 1:02d}", name=("Inbound" if i < 2 else "Outbound") + f" door {i % 2 + 1}",
                      direction="IN" if i < 2 else "OUT", bin_id=b.id))
    ALL = ["PICK", "PUTAWAY", "REPLEN", "REARR", "XDOCK"]
    Q = lambda c, n, aas, acts: _add(db, m.Queue(warehouse_id=w1.id, code=c, name=n, activity_area_ids=[a.id for a in aas], task_types=acts))
    qpk, qpw, qin, qbk, qdk = Q("PICK-FAST", "Picking — pick area", [aap], ["PICK"]), Q("PTWY-RACK", "Putaway — pick area", [aap], ["PUTAWAY"]), \
        Q("INTERNAL", "Replenishment & rearrangement", [aap], ["REPLEN", "REARR"]), Q("BULK", "All bulk floor moves", [aab], ALL), \
        Q("DOCK", "Dock & cross-dock moves", [aad], ALL)
    RT = lambda c, n, lvl: _add(db, m.ResourceType(warehouse_id=w1.id, code=c, name=n, max_level=lvl))
    rtw, rtr, rtf = RT("PICKER", "Walking picker (RF gun)", 1), RT("REACH", "Reach truck", 3), RT("FORK", "Counterbalance forklift", 1)
    for c, n, t, qs, st in (("RES-01", "Ravi Kumar", rtw, [qpk], "AVAILABLE"), ("RES-02", "Anil Sharma", rtr, [qpw, qin, qpk], "AVAILABLE"),
                            ("RES-03", "Suresh N", rtf, [qbk, qdk, qin], "LOGGED_OFF")):
        db.add(m.Resource(warehouse_id=w1.id, code=c, name=n, resource_type_id=t.id, queue_ids=[q.id for q in qs], status=st))
    db.add(m.WorkCenter(warehouse_id=w1.id, code="PACK-01", name="Outbound packing station", kind="PACK", bin_id=d_out[0].id))
    cfg = db.get(m.WarehouseConfig, w1.id)
    cfg.stage_in_bin_id, cfg.stage_out_bin_id, cfg.xd_in_bin_id, cfg.xd_out_bin_id = d_in[0].id, d_out[0].id, d_in[0].id, d_out[0].id
    cfg.xdock_opportunistic = True
    db.flush()
    ctx = WhCtx(db, w1.id, "ADMIN")
    rk = sorted([b for b in ctx.bins.values() if b.rack_id == rack_a.id], key=lambda b: (b.y, b.x, b.z))
    for b, mat, q, bt_, ex in ((faces[0], rm1, 18, "", None), (faces[1], rm2, 12, "B-2401", date(2027, 3, 31)), (faces[2], rm3, 40, "", None),
                               (bulk[0], rm1, 300, "", None), (bulk[1], rm2, 400, "B-2401", date(2027, 3, 31)),
                               (bulk[1], rm2, 180, "B-2312", date(2026, 11, 30)), (bulk[2], rm3, 260, "", None), (bulk[3], pk, 500, "", None),
                               (rk[0], sf, 10, "SB-01", date(2028, 1, 31))):
        ctx.add_stock(b.id, mat.id, q, bt_, "", ex)
    ctx.add_stock(rk[3].id, fg.id, 1, "", "SN-00001")
    ctx.add_stock(rk[3].id, fg.id, 1, "", "SN-00002")
    a = _add(db, m.Asn(warehouse_id=w1.id, number=next_number(db, w1.id, "ASN", "ASN"), vendor="Precision Castings Ltd", eta=date.today()))
    db.add(m.AsnLine(asn_id=a.id, material_id=rm1.id, qty=120))
    db.add(m.AsnLine(asn_id=a.id, material_id=rm2.id, qty=200, tracking_no="B-2405", expiry=date(2027, 9, 30)))
    for cust, lines in (("Hindustan Pumps", [(fg, 3)]), ("Delta Engineering", [(rm3, 25), (rm1, 15)]), ("Kaveri Motors", [(rm2, 650)])):
        o = _add(db, m.SalesOrder(warehouse_id=w1.id, number=next_number(db, w1.id, "SO", "SO"), customer=cust, order_date=date.today()))
        for mat, q in lines:
            db.add(m.SalesOrderLine(order_id=o.id, material_id=mat.id, qty=q))
    xo = _add(db, m.CrossdockOrder(warehouse_id=w1.id, number=next_number(db, w1.id, "XDO", "XDO"), kind="PXD",
                                   from_party="Precision Castings Ltd", to_party="Delta Engineering"))
    db.add(m.CrossdockOrderLine(order_id=xo.id, material_id=rm1.id, qty=30))
    db.add(m.CrossdockOrderLine(order_id=xo.id, material_id=rm3.id, qty=20))

    # ── WH02 Chennai DC and XD01 Hosur hub ──
    def small(code, name, typ, city, district, pin, line1, line2, contact, phone):
        w = _wh(db, code, name, typ, city, district, "33", pin, line1, line2, contact, phone)
        r_ = _st(db, w, "RCV", "Inbound docks", "RECEIVING", 0, 9)
        s_ = _st(db, w, "SHP", "Outbound docks", "SHIPPING", 9, 0)
        dk = _add(db, m.BinType(warehouse_id=w.id, code="DK", name="Dock door / lane", max_qty=2000, max_weight=9000, max_volume=60))
        ad = _add(db, m.ActivityArea(warehouse_id=w.id, code="DOCK", name="Docks & lanes"))
        ins = [_bin(db, w, f"GR-{i + 1:02d}", r_, i, 0, bt=dk, aa=ad) for i in range(3)]
        outs = [_bin(db, w, f"GI-{i + 1:02d}", s_, i + 6, 0, bt=dk, aa=ad) for i in range(3)]
        for i, b in enumerate(ins + outs):
            db.add(m.Door(warehouse_id=w.id, code=f"DOOR-{i + 1:02d}", name=("Inbound" if i < 3 else "Outbound") + f" door {i % 3 + 1}",
                          direction="IN" if i < 3 else "OUT", bin_id=b.id))
        qs = [_add(db, m.Queue(warehouse_id=w.id, code="DOCK", name="Dock & cross-dock moves", activity_area_ids=[ad.id], task_types=ALL))]
        cfg = db.get(m.WarehouseConfig, w.id)
        cfg.stage_in_bin_id, cfg.stage_out_bin_id, cfg.xd_out_bin_id = ins[0].id, outs[0].id, outs[0].id
        if typ == "XD":
            x_ = _st(db, w, "XST", "Cross-dock staging lanes", "STAGING", 5, 5)
            lanes = [_bin(db, w, f"XL-{i + 1:02d}", x_, i + 2, 2, bt=dk, aa=ad) for i in range(4)]
            cfg.xd_in_bin_id = lanes[0].id
        else:
            st = _st(db, w, "RK", "Pallet racking", "STORAGE", 1, 1)
            sec = _add(db, m.StorageSection(warehouse_id=w.id, storage_type_id=st.id, code="S01", name="Standard"))
            rb = _add(db, m.BinType(warehouse_id=w.id, code="RK", name="Pallet rack slot", max_qty=80, max_weight=600, max_volume=2.5))
            am = _add(db, m.ActivityArea(warehouse_id=w.id, code="MAIN", name="Racking"))
            qs.append(_add(db, m.Queue(warehouse_id=w.id, code="RACK", name="Rack moves", activity_area_ids=[am.id], task_types=ALL)))
            rk_ = _add(db, m.Rack(warehouse_id=w.id, code="RACK-01", name="Aisles 1–2", storage_type_id=st.id, section_id=sec.id,
                                  bin_type_id=rb.id, activity_area_id=am.id, x1=0, y1=2, x2=5, y2=2, aisle_from=1, aisle_to=2,
                                  aisle_gap=2, level_from=1, level_to=2))
            c2 = WhCtx(db, w.id, "ADMIN")
            racks.generate(c2, rk_)
            cfg.xd_in_bin_id = ins[0].id
            cfg.xdock_opportunistic = True
            rbins = sorted([b for b in c2.bins.values() if b.rack_id == rk_.id], key=lambda b: (b.y, b.x, b.z))
            c2.add_stock(rbins[0].id, rm3.id, 60)
            c2.add_stock(rbins[3].id, rm1.id, 40)
        rt = _add(db, m.ResourceType(warehouse_id=w.id, code="FORK", name="Forklift", max_level=2))
        db.add(m.Resource(warehouse_id=w.id, code=f"{code}-R1", name="Kiran (dock lead)" if typ == "XD" else "Meena R",
                          resource_type_id=rt.id, queue_ids=[q.id for q in qs], status="AVAILABLE"))
        return w

    w2 = small("WH02", "Regional DC Chennai", "DC", "Chennai", "Kancheepuram", "602117", "No. 18, SIPCOT Industrial Park",
               "Irungattukottai, Sriperumbudur", "S. Lakshmi", "+91 44 4000 2200")
    w3 = small("XD01", "Hosur cross-dock hub", "XD", "Hosur", "Krishnagiri", "635126", "Survey No. 77, SIPCOT Phase II",
               "Mookandapalli", "Kiran Kumar", "+91 4344 400 330")
    for pl, c, n, w in ((p1, "0001", "Finished goods & RM", w1), (p1, "0002", "Transit / cross-dock", w3),
                        (p2, "0001", "Regional stock", w2), (p2, "0900", "Scrap (not WM)", None)):
        db.add(m.StorageLocation(plant_id=pl.id, code=c, name=n, warehouse_id=w.id if w else None))
    t = _add(db, m.StockTransfer(number=next_number(db, 0, "STO", "STO"), from_wh_id=w1.id, via_wh_id=w3.id, to_wh_id=w2.id))
    db.add(m.StockTransferLine(transfer_id=t.id, material_id=rm3.id, qty=40))
    db.add(m.StockTransferLine(transfer_id=t.id, material_id=rm1.id, qty=20))
    db.add(m.StockTransferEvent(transfer_id=t.id, message="Created: WH01 → XD01 → WH02"))
    db.add(m.AuditLog(warehouse_id=None, role="ADMIN", action="SETUP", detail="Demo data loaded (3 warehouses)"))
    db.commit()
    return {"warehouses": [w1.id, w2.id, w3.id]}


def reset_and_seed():
    m.Base.metadata.drop_all(engine)
    m.Base.metadata.create_all(engine)
    with SessionLocal() as db:
        return seed(db)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        print(reset_and_seed())
    else:
        m.Base.metadata.create_all(engine)
        with SessionLocal() as db:
            print(seed(db))
