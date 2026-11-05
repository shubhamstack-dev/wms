"""End-to-end API tests. Run against a throwaway MySQL database:

    TEST_DATABASE_URL=mysql+pymysql://wms:wms_pass@localhost:3306/wms_test pytest -q
"""
import os
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "mysql+pymysql://wms:wms_pass@localhost:3306/wms_test?charset=utf8mb4")

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.seed import reset_and_seed

from app import auth
from sqlalchemy import delete
from app.db import SessionLocal

# filled with real login tokens by the fixture; every request without its own
# headers goes out as the operator
ADMIN, OP = {}, {}


def _user(db, name, role):
    u = auth.AppUser(username=name, password_hash=auth.hash_password("secret-pass"), role=role, active=True)
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def c():
    reset_and_seed()
    auth.create_tables()
    with SessionLocal() as db:
        db.execute(delete(auth.AppUser))
        db.commit()
        ADMIN.clear(); ADMIN["Authorization"] = "Bearer " + auth.make_token(_user(db, "admin", "ADMIN"))
        OP.clear(); OP["Authorization"] = "Bearer " + auth.make_token(_user(db, "op", "OPERATOR"))
    with TestClient(app) as client:
        client.headers.update(OP)
        yield client


def wh(c, code):
    return next(w for w in c.get("/api/warehouses").json() if w["code"] == code)


def mat(c, code):
    return next(x for x in c.get("/api/materials").json() if x["code"] == code)


def ok(resp, code=200):
    assert resp.status_code == code, resp.text
    return resp.json()


def test_api_surface(c):
    paths = c.get("/openapi.json").json()["paths"]
    assert len(paths) >= 60
    assert "/api/warehouses/{wh}/racks/preview" in paths and "/api/transfers/{tid}/{action}" in paths


def test_gstin_validation(c):
    assert c.get("/api/gst/validate", params={"gstin": "27AAPFU0939F1ZV"}).json()["ok"]
    bad = c.get("/api/gst/validate", params={"gstin": "27AAPFU0939F1ZX"}).json()
    assert not bad["ok"] and "Check character" in bad["msg"]


def test_enterprise_master_data(c):
    ws = c.get("/api/warehouses").json()
    assert [w["code"] for w in ws] == ["WH01", "WH02", "XD01"]
    assert all(w["gstin_valid"] and not w["issues"] for w in ws)
    w1 = wh(c, "WH01")
    body = {k: w1[k] for k in ("code", "name", "type", "addr_line1", "city", "state_code", "pin")}
    r = c.put(f"/api/warehouses/{w1['id']}", json={**body, "gstin": "33AABCB1234F1ZF"}, headers=ADMIN)
    assert r.status_code == 422 and "state" in r.text            # TN GSTIN on a Karnataka address
    r = c.put(f"/api/warehouses/{w1['id']}", json={**body, "gstin": "29AABCB1234F1ZX"}, headers=ADMIN)
    assert r.status_code == 422                                   # wrong check character
    assert c.put(f"/api/warehouses/{w1['id']}", json={**body, "pin": "12"}, headers=ADMIN).status_code == 422


def test_permissions(c):
    w1 = wh(c, "WH01")
    r = c.post(f"/api/warehouses/{w1['id']}/asns", json={"lines": [{"material_id": mat(c, "RM-303")["id"], "qty": 1}]}, headers=OP)
    assert r.status_code == 403


def test_inbound_putaway_with_resources(c):
    w1 = wh(c, "WH01")["id"]
    asn = c.get(f"/api/warehouses/{w1}/asns").json()[0]
    res = ok(c.post(f"/api/warehouses/{w1}/asns/{asn['id']}/receive", headers=ADMIN))
    doc = ok(c.get(f"/api/warehouses/{w1}/documents/{res['document_id']}"))
    assert doc["type"] == "PUTAWAY" and sum(t["qty"] for t in doc["tasks"]) == 320
    assert all(t["wo_number"] for t in doc["tasks"])               # every WT belongs to a warehouse order
    before = sum(s["qty"] for s in c.get(f"/api/warehouses/{w1}/stock").json())
    for _ in range(10):                                             # resources pull work until nothing is left
        ok(c.post(f"/api/warehouses/{w1}/resources/auto-assign", headers=ADMIN))
        mon = ok(c.get(f"/api/warehouses/{w1}/resource-monitor"))
        busy = [r for r in mon["resources"] if r["current"]]
        if not busy:
            break
        for r in busy:
            ok(c.post(f"/api/warehouses/{w1}/warehouse-orders/{r['current']['id']}/confirm", headers=ADMIN))
    left = [w for w in c.get(f"/api/warehouses/{w1}/warehouse-orders", params={"status": "open"}).json()]
    for w in left:                                                  # e.g. bulk queue whose forklift driver is logged off
        ok(c.post(f"/api/warehouses/{w1}/warehouse-orders/{w['id']}/confirm", headers=ADMIN))
    after = sum(s["qty"] for s in c.get(f"/api/warehouses/{w1}/stock").json())
    assert round(after - before, 3) == 320
    assert ok(c.get(f"/api/warehouses/{w1}/documents/{res['document_id']}"))["status"] == "DONE"


def test_wave_bom_explosion_shortage_and_opportunistic_xdock(c):
    w1 = wh(c, "WH01")["id"]
    orders = c.get(f"/api/warehouses/{w1}/orders").json()
    res = ok(c.post(f"/api/warehouses/{w1}/waves", json={"order_ids": [o["id"] for o in orders]}, headers=ADMIN))
    doc = ok(c.get(f"/api/warehouses/{w1}/documents/{res['document_id']}"))
    assert any(t["level"] == 1 and t["material_code"] == "SF-200" for t in doc["tasks"])   # FG-100 short by 1 → exploded
    assert [(s["material_code"], s["qty"]) for s in doc["shortages"]] == [("RM-302", 58)]
    # FEFO: the batch expiring 2026-11-30 is picked before 2027-03-31
    rm2 = [t for t in doc["tasks"] if t["material_code"] == "RM-302" and t["source_bin"] == "BLK-002"]
    assert rm2[0]["tracking_no"] == "B-2312"
    # a walking picker (max level 1) never gets a WO that touches level 2–3 bins
    mon = ok(c.get(f"/api/warehouses/{w1}/resource-monitor"))
    picker = next(r for r in mon["resources"] if r["code"] == "RES-01")
    for w in c.get(f"/api/warehouses/{w1}/warehouse-orders", params={"status": "open"}).json():
        if picker["id"] in w["eligible"]:
            assert all(not l["bin"].endswith(("L02", "L03")) for l in w["lines"])
    # receipt with the short batch material is cross-docked to the staging bin instead of putaway
    asn = c.get(f"/api/warehouses/{w1}/asns").json()[0]
    r = ok(c.post(f"/api/warehouses/{w1}/asns/{asn['id']}/receive", headers=ADMIN))
    assert r["crossdocked_qty"] == 58
    xd = ok(c.get(f"/api/warehouses/{w1}/crossdock-orders"))
    assert xd["opportunistic"][0]["qty"] == 58 and not xd["backorders"]


def test_racks_preview_generate_and_designer(c):
    w1 = wh(c, "WH01")["id"]
    za = next(s for s in c.get(f"/api/warehouses/{w1}/storage-types").json() if s["code"] == "ZA")
    body = {"code": "RACK-B", "storage_type_id": za["id"], "x1": 0, "y1": 2, "x2": 5, "y2": 2, "aisle_from": 1, "aisle_to": 1,
            "level_from": 1, "level_to": 3, "pattern": "A{A}-R{P}-L{L}"}
    p = ok(c.post(f"/api/warehouses/{w1}/racks/preview", json=body))
    assert p["counts"] == {"exists": 12, "new": 6}                # 4 positions already exist, 2 new × 3 levels
    body2 = {**body, "x1": 0, "y1": 8, "x2": 7, "y2": 8, "aisle_to": 2, "aisle_gap": 2, "pattern": "{ST}-{A}-{P}-{L}"}
    r = ok(c.post(f"/api/warehouses/{w1}/racks", params={"generate": True}, json=body2, headers=ADMIN))
    assert r["made"] == 48 and r["skipped"] == 0
    assert ok(c.post(f"/api/warehouses/{w1}/racks/{r['id']}/generate", headers=ADMIN))["made"] == 0   # idempotent
    bins = c.get(f"/api/warehouses/{w1}/bins").json()
    assert any(b["code"] == "ZA-02-08-03" and (b["x"], b["y"], b["z"]) == (7, 10, 3) for b in bins)
    # designer: draw, assign, delete
    d = ok(c.post(f"/api/warehouses/{w1}/designer/draw", json={"x0": 12, "y0": 1, "x1": 14, "y1": 1, "storage_type_id": za["id"],
                                                                "levels": 2}, headers=ADMIN))
    assert d["made"] == 6
    new = [b["id"] for b in c.get(f"/api/warehouses/{w1}/bins").json() if b["x"] >= 12 and b["z"] == 1]
    aa = c.get(f"/api/warehouses/{w1}/activity-areas").json()[0]
    a = ok(c.post(f"/api/warehouses/{w1}/designer/assign", json={"bin_ids": new, "all_levels": True, "activity_area_id": aa["id"]},
                  headers=ADMIN))
    assert a["updated"] == 6
    assert ok(c.post(f"/api/warehouses/{w1}/designer/delete", json={"ids": new}, headers=ADMIN))["deleted"] == 3


def test_planned_crossdock(c):
    w1 = wh(c, "WH01")["id"]
    xo = ok(c.get(f"/api/warehouses/{w1}/crossdock-orders"))["orders"][0]
    stock0 = sum(s["qty"] for s in c.get(f"/api/warehouses/{w1}/stock").json())
    ok(c.post(f"/api/warehouses/{w1}/crossdock-orders/{xo['id']}/receive", headers=ADMIN))
    x = ok(c.get(f"/api/warehouses/{w1}/crossdock-orders"))["orders"][0]
    assert x["status"] == "IN_XDOCK" and x["tasks"] == 2
    ok(c.post(f"/api/warehouses/{w1}/crossdock-orders/{xo['id']}/confirm-moves", headers=ADMIN))
    assert ok(c.get(f"/api/warehouses/{w1}/crossdock-orders"))["orders"][0]["status"] == "READY"
    ok(c.post(f"/api/warehouses/{w1}/crossdock-orders/{xo['id']}/goods-issue", headers=ADMIN))
    x = ok(c.get(f"/api/warehouses/{w1}/crossdock-orders"))["orders"][0]
    assert x["status"] == "SHIPPED" and "dwell_minutes" in x
    assert sum(s["qty"] for s in c.get(f"/api/warehouses/{w1}/stock").json()) == stock0     # flowed through, nothing stored


def test_transfer_through_hub(c):
    t = c.get("/api/transfers").json()[0]
    for action, status in (("release", "RELEASED"), ("pick-and-ship", "TO_HUB"), ("hub-receive", "AT_HUB"),
                           ("hub-confirm", "AT_HUB"), ("hub-dispatch", "IN_TRANSIT")):
        ok(c.post(f"/api/transfers/{t['id']}/{action}", headers=ADMIN))
        assert c.get("/api/transfers").json()[0]["status"] == status, action
    xd01 = wh(c, "XD01")["id"]
    assert ok(c.get(f"/api/warehouses/{xd01}/stock")) == []          # hub kept nothing
    assert not [d for d in c.get(f"/api/warehouses/{xd01}/documents").json() if d["type"] == "PUTAWAY"]
    ov = {r["code"]: r for r in c.get("/api/stock-overview").json()}
    assert ov["RM-303"]["in_transit"] == 40
    ok(c.post(f"/api/transfers/{t['id']}/receive", headers=ADMIN))
    t2 = c.get("/api/transfers").json()[0]
    assert t2["status"] == "COMPLETED" and len(t2["events"]) >= 8
    wh2 = wh(c, "WH02")["id"]
    assert any(d["type"] == "PUTAWAY" for d in c.get(f"/api/warehouses/{wh2}/documents").json())


def test_transfer_advances_through_normal_operations(c):
    t = c.get("/api/transfers").json()[0]
    ok(c.post(f"/api/transfers/{t['id']}/release", headers=ADMIN))
    w1 = wh(c, "WH01")["id"]
    o = next(o for o in c.get(f"/api/warehouses/{w1}/orders").json() if o["transfer_id"] == t["id"])
    res = ok(c.post(f"/api/warehouses/{w1}/waves", json={"order_ids": [o["id"]]}, headers=ADMIN))
    ids = [x["id"] for x in ok(c.get(f"/api/warehouses/{w1}/documents/{res['document_id']}"))["tasks"]]
    ok(c.post(f"/api/warehouses/{w1}/tasks/confirm", json={"ids": ids}, headers=OP))
    assert c.get("/api/transfers").json()[0]["status"] == "TO_HUB"
    xd01 = wh(c, "XD01")["id"]
    asn = next(a for a in c.get(f"/api/warehouses/{xd01}/asns").json() if a["status"] == "OPEN")
    r = ok(c.post(f"/api/warehouses/{xd01}/asns/{asn['id']}/receive", headers=ADMIN))     # normal inbound endpoint at the hub
    assert r["crossdock_order"] and c.get("/api/transfers").json()[0]["status"] == "AT_HUB"


def test_new_warehouse_copy_and_exports(c):
    w1 = wh(c, "WH01")
    plant = c.get("/api/plants").json()[0]
    r = ok(c.post("/api/warehouses", json={"code": "wh03", "name": "Pune DC", "copy_from_id": w1["id"], "copy_bins": True,
                                           "plant_id": plant["id"], "sloc_code": "0005"}, headers=ADMIN))
    assert r["code"] == "WH03" and r["bins"] == w1["bins"] and r["units"] == 0
    assert r["storage_locations"] == [f"{plant['code']}/0005"]
    j = ok(c.get("/api/exports/gst-master.json"))
    assert {x["warehouse"] for x in j["warehouses"]} == {"WH01", "WH02", "XD01", "WH03"}
    assert "29AABCB1234F1Z4" in c.get("/api/exports/gst-master.csv").text
    t = ok(c.get("/api/exports/transfers.json"))["transfers"][0]
    assert t["from"]["gstin"].startswith("29") and t["to"]["gstin"].startswith("33") and not t["sameGstin"]


def test_materials_and_bom(c):
    r = ok(c.post("/api/materials", json={"code": "tst-1", "name": "Test", "tracking": "BATCH"}, headers=ADMIN))
    assert r["code"] == "TST-1"
    assert c.post("/api/materials", json={"code": "TST-1"}, headers=ADMIN).status_code == 400
    ok(c.put(f"/api/boms/{r['id']}", json={"components": [{"material_id": mat(c, "RM-301")["id"], "qty": 2}]}, headers=ADMIN))
    assert any(b["parent_material_id"] == r["id"] for b in c.get("/api/boms").json())


def test_import_from_html_app(c):
    import json, pathlib
    data = json.loads((pathlib.Path(__file__).parent / "fixtures" / "legacy-export.json").read_text())
    assert c.post("/api/admin/import-legacy", json=data, headers=ADMIN).status_code == 400   # database not empty
    r = ok(c.post("/api/admin/import-legacy", params={"replace": True}, json=data, headers=ADMIN))
    assert r["imported"]["warehouses"] == 3 and r["imported"]["bins"] == 80 and not r["warnings"]
    ws = c.get("/api/warehouses").json()
    assert all(w["gstin_valid"] for w in ws) and ws[0]["storage_locations"] == ["1000/0001"]
    w1 = ws[0]["id"]
    orders = c.get(f"/api/warehouses/{w1}/orders").json()
    ok(c.post(f"/api/warehouses/{w1}/waves", json={"order_ids": [o["id"] for o in orders]}, headers=ADMIN))
    new = ok(c.post(f"/api/warehouses/{w1}/orders", json={"lines": [{"material_id": mat(c, "RM-303")["id"], "qty": 1}]}, headers=ADMIN))
    assert new["number"] == "SO-0004"                     # number range continues after imported numbers


def test_login_and_users():
    auth.create_tables()
    with SessionLocal() as db:
        db.execute(delete(auth.AppUser))
        db.commit()
    with TestClient(app) as anon:
        assert anon.get("/api/warehouses").status_code == 401           # not logged in
        assert anon.get("/api/health").status_code == 200
        assert ok(anon.get("/api/auth/status"))["needs_setup"] is True
        tok = ok(anon.post("/api/auth/setup", json={"username": "Boss", "password": "longpassword"}))
        assert tok["user"] == {"id": tok["user"]["id"], "username": "boss", "role": "ADMIN", "active": True}
        assert anon.post("/api/auth/setup", json={"username": "other", "password": "longpassword"}).status_code == 409
        assert anon.post("/api/auth/login", json={"username": "boss", "password": "wrong"}).status_code == 401
        adm = {"Authorization": "Bearer " + ok(anon.post("/api/auth/login",
                                                         json={"username": "boss", "password": "longpassword"}))["token"]}
        assert anon.get("/api/warehouses", headers=adm).status_code == 200
        assert anon.get("/api/warehouses", headers={"Authorization": "Bearer junk.sig"}).status_code == 401
        op = ok(anon.post("/api/users", headers=adm, json={"username": "ravi", "password": "12345678", "role": "OPERATOR"}))
        oph = {"Authorization": "Bearer " + ok(anon.post("/api/auth/login",
                                                         json={"username": "ravi", "password": "12345678"}))["token"]}
        assert anon.get("/api/users", headers=oph).status_code == 403
        assert anon.post("/api/admin/load-demo", headers=oph).status_code == 403
        assert anon.put(f"/api/users/{tok['user']['id']}", headers=adm, json={"role": "OPERATOR"}).status_code == 400
        ok(anon.put(f"/api/users/{op['id']}", headers=adm, json={"active": False}))
        assert anon.get("/api/warehouses", headers=oph).status_code == 401   # deactivated user is out at once
        ok(anon.delete(f"/api/users/{op['id']}", headers=adm))
