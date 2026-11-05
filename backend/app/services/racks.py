"""Racks (bin structures): start point → end point, aisles, positions, levels → generated bins.
Also the graphical designer operations: draw bins in a rectangle, bulk-assign org units, delete empty bins."""
import re
from .. import models as m
from ..core import BizError
from .engine import WhCtx

WHY = {"code": "code already used by another bin", "pos": "position already has a bin",
       "dup": "duplicate code in this rack", "out": "outside the grid (negative X/Y)"}
_TOK = re.compile(r"\{(ST|SEC|A|P|L)(\d)?\}", re.I)


def rack_code(r: dict, st_code: str, sec_code: str, A: int, P: int, L: int) -> str:
    vals = {"ST": st_code or "", "SEC": sec_code or "", "A": A, "P": P, "L": L}

    def rep(mo):
        k, w = mo.group(1).upper(), mo.group(2)
        if k in ("ST", "SEC"):
            return vals[k]
        return str(vals[k]).zfill(int(w) if w else max(1, int(r.get("pad") or 2)))
    return _TOK.sub(rep, r.get("pattern") or "{A}-{P}-{L}").upper()


def plan(ctx: WhCtx, r: dict, own_bin_ids: set | None = None) -> dict:
    st = ctx.types.get(r["storage_type_id"])
    if st is None:
        raise BizError("Choose a storage type for the rack")
    sec = ctx.db.get(m.StorageSection, r["section_id"]) if r.get("section_id") else None
    x1, y1, x2, y2 = (int(r[k]) for k in ("x1", "y1", "x2", "y2"))
    horiz = abs(x2 - x1) >= abs(y2 - y1)
    length = min(200, (abs(x2 - x1) if horiz else abs(y2 - y1)) + 1)
    dp = (1 if (x2 - x1 if horiz else y2 - y1) >= 0 else -1)
    na = max(1, min(40, int(r["aisle_to"]) - int(r["aisle_from"]) + 1))
    nl = max(1, min(20, int(r["level_to"]) - int(r["level_from"]) + 1))
    gap, step = max(1, int(r.get("aisle_gap") or 1)), max(1, int(r.get("pos_step") or 1))
    codes = {b.code: b for b in ctx.bins.values()}
    occ = {(b.x, b.y, b.z): b for b in ctx.bins.values()}
    items, seen = [], set()
    for ai in range(na):
        for i in range(length):
            for li in range(nl):
                A, P, L = int(r["aisle_from"]) + ai, int(r["pos_from"]) + i * step, int(r["level_from"]) + li
                x = x1 + i * dp if horiz else x1 + ai * gap
                y = y1 + ai * gap if horiz else y1 + i * dp
                code = rack_code(r, st.code, sec.code if sec else "", A, P, L)
                cb, ob = codes.get(code), occ.get((x, y, L))
                status = "new"
                if x < 0 or y < 0:
                    status = "out"
                elif cb is not None and cb is ob:
                    status = "exists"
                elif cb is not None:
                    status = "code"
                elif ob is not None:
                    status = "pos"
                elif code in seen:
                    status = "dup"
                seen.add(code)
                items.append({"code": code, "x": x, "y": y, "z": L, "status": status})
    counts = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {"items": items, "horizontal": horiz, "positions": length, "aisles": na, "levels": nl, "counts": counts,
            "conflicts": [{"code": it["code"], "why": WHY[it["status"]]} for it in items if it["status"] in WHY][:50]}


def _rack_dict(rk: m.Rack) -> dict:
    return {c.name: getattr(rk, c.name) for c in rk.__table__.columns}


def generate(ctx: WhCtx, rk: m.Rack) -> dict:
    p = plan(ctx, _rack_dict(rk))
    bt = ctx.db.get(m.BinType, rk.bin_type_id) if rk.bin_type_id else None
    sec_ok = rk.section_id and (s := ctx.db.get(m.StorageSection, rk.section_id)) and s.storage_type_id == rk.storage_type_id
    q = (bt.max_qty if bt and bt.max_qty else 100)
    made = 0
    for it in p["items"]:
        if it["status"] == "exists":
            b = next(b for b in ctx.bins.values() if b.code == it["code"])
            b.rack_id = rk.id
        if it["status"] != "new":
            continue
        b = m.Bin(warehouse_id=ctx.wh_id, code=it["code"], storage_type_id=rk.storage_type_id,
                  section_id=rk.section_id if sec_ok else None, bin_type_id=rk.bin_type_id,
                  activity_area_id=rk.activity_area_id, rack_id=rk.id, x=it["x"], y=it["y"], z=it["z"],
                  max_qty=bt.max_qty if bt and bt.max_qty else 100, max_weight=bt.max_weight if bt else 0,
                  max_volume=bt.max_volume if bt else 0, pick_face=rk.pick_face,
                  min_qty=round(q * 0.2) if rk.pick_face else 0, replen_to=q if rk.pick_face else 0)
        ctx.db.add(b)
        ctx.db.flush()
        ctx.bins[b.id] = b
        made += 1
    skipped = len(p["items"]) - made - p["counts"].get("exists", 0)
    ctx.log("ORG", f"Rack {rk.code}: {made} bins generated ({rk.x1},{rk.y1}) → ({rk.x2},{rk.y2})"
                   + (f", {skipped} conflicts skipped" if skipped else ""))
    return {"made": made, "skipped": skipped, "existing": p["counts"].get("exists", 0)}


def delete_empty_bins(ctx: WhCtx, bins: list[m.Bin]) -> dict:
    deleted = kept = 0
    for b in bins:
        if ctx.bin_qty(b.id) > 0:
            kept += 1
            continue
        ctx.db.delete(b)
        ctx.bins.pop(b.id, None)
        deleted += 1
    ctx.db.flush()
    return {"deleted": deleted, "kept_with_stock": kept}


def draw_bins(ctx: WhCtx, d: dict) -> dict:
    st = ctx.types.get(d["storage_type_id"])
    if st is None:
        raise BizError("Choose a storage type")
    bt = ctx.db.get(m.BinType, d["bin_type_id"]) if d.get("bin_type_id") else None
    sec = ctx.db.get(m.StorageSection, d["section_id"]) if d.get("section_id") else None
    pfx = (d.get("prefix") or st.code).upper()
    levels, z0 = max(1, min(9, int(d.get("levels") or 1))), int(d.get("level") or 1)
    codes, occ = {b.code for b in ctx.bins.values()}, {(b.x, b.y, b.z) for b in ctx.bins.values()}
    q = bt.max_qty if bt and bt.max_qty else 100
    made = skipped = 0
    for y in range(min(d["y0"], d["y1"]), max(d["y0"], d["y1"]) + 1):
        for x in range(min(d["x0"], d["x1"]), max(d["x0"], d["x1"]) + 1):
            for z in range(z0, z0 + levels):
                if (x, y, z) in occ:
                    skipped += 1
                    continue
                code = f"{pfx}-{y + 1:02d}-{x + 1:02d}" + (f"-{z:02d}" if levels > 1 or z > 1 else "")
                k = 1
                while code in codes:
                    code = f"{pfx}-{y + 1:02d}-{x + 1:02d}-{z:02d}{chr(64 + k)}"
                    k += 1
                codes.add(code)
                b = m.Bin(warehouse_id=ctx.wh_id, code=code, storage_type_id=st.id,
                          section_id=sec.id if sec and sec.storage_type_id == st.id else None,
                          bin_type_id=bt.id if bt else None, activity_area_id=d.get("activity_area_id") or None,
                          x=x, y=y, z=z, max_qty=q, max_weight=bt.max_weight if bt else 0, max_volume=bt.max_volume if bt else 0,
                          pick_face=bool(d.get("pick_face")), min_qty=round(q * 0.2) if d.get("pick_face") else 0,
                          replen_to=q if d.get("pick_face") else 0)
                ctx.db.add(b)
                made += 1
    ctx.db.flush()
    if made:
        ctx.log("ORG", f"Designer: {made} bins drawn in {st.code}")
    return {"made": made, "skipped": skipped}


def bulk_assign(ctx: WhCtx, d: dict) -> dict:
    """Fields: None = keep, 0 = clear (section / bin type / activity area)."""
    ids = set(d["bin_ids"])
    sel = [b for b in ctx.bins.values() if b.id in ids]
    if d.get("all_levels"):
        pos = {(b.x, b.y) for b in sel}
        sel = [b for b in ctx.bins.values() if (b.x, b.y) in pos]
    ok = skip = 0
    for b in sel:
        st_id = d.get("storage_type_id")
        if st_id and st_id != b.storage_type_id:
            if ctx.bin_qty(b.id) > 0:
                skip += 1
                continue
            b.storage_type_id = st_id
            sec = ctx.db.get(m.StorageSection, b.section_id) if b.section_id else None
            if sec and sec.storage_type_id != st_id:
                b.section_id = None
        if d.get("section_id") == 0:
            b.section_id = None
        elif d.get("section_id"):
            sec = ctx.db.get(m.StorageSection, d["section_id"])
            if not sec or sec.storage_type_id != b.storage_type_id:
                skip += 1
                continue
            b.section_id = sec.id
        if d.get("bin_type_id") == 0:
            b.bin_type_id = None
        elif d.get("bin_type_id"):
            bt = ctx.db.get(m.BinType, d["bin_type_id"])
            b.bin_type_id = bt.id
            if bt.max_qty > 0: b.max_qty = bt.max_qty
            if bt.max_weight > 0: b.max_weight = bt.max_weight
            if bt.max_volume > 0: b.max_volume = bt.max_volume
        if d.get("activity_area_id") == 0:
            b.activity_area_id = None
        elif d.get("activity_area_id"):
            b.activity_area_id = d["activity_area_id"]
        if d.get("pick_face") is not None:
            b.pick_face = bool(d["pick_face"])
            if b.pick_face and not b.replen_to:
                b.replen_to, b.min_qty = b.max_qty, round(b.max_qty * 0.2)
        if d.get("blocked") is not None:
            b.blocked = bool(d["blocked"])
        ok += 1
    ctx.log("ORG", f"Designer: {ok} bins updated" + (f", {skip} skipped" if skip else ""))
    return {"updated": ok, "skipped": skip}
