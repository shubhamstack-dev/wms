"""Warehouse execution engine — a per-request, per-warehouse working context.

Ported from the single-file prototype: capacity (qty / weight / volume), putaway strategies
(nearest / fixed / consolidate / capacity + mixed-storage rule), pick strategies
(FEFO / FIFO / LIFO / nearest / fixed, pick-face first), BOM explosion, warehouse documents,
warehouse tasks (WT), warehouse orders (WO) grouped by activity area and path sequence,
queue determination and resource assignment.
"""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .. import models as m
from ..core import BizError, next_number, next_int, audit, utcnow

FAR = date(9999, 12, 31)
EPS = 1e-6


class WhCtx:
    def __init__(self, db: Session, wh_id: int, role: str = "SYSTEM"):
        self.db, self.wh_id, self.role = db, wh_id, role
        self.wh = db.get(m.Warehouse, wh_id)
        if self.wh is None:
            raise BizError(f"Warehouse {wh_id} not found")
        self.cfg = db.get(m.WarehouseConfig, wh_id)
        if self.cfg is None:
            self.cfg = m.WarehouseConfig(warehouse_id=wh_id)
            db.add(self.cfg)
            db.flush()
        W = lambda model: select(model).where(model.warehouse_id == wh_id)
        self.types = {t.id: t for t in db.scalars(W(m.StorageType))}
        self.bins = {b.id: b for b in db.scalars(W(m.Bin))}
        self.stock = list(db.scalars(W(m.Stock)))
        self.mats = {x.id: x for x in db.scalars(select(m.Material))}
        self._seq = (db.scalar(select(func.max(m.Stock.gr_seq))) or 0) + 1
        self._boms = None

    # ── logging ──
    def log(self, action: str, detail: str):
        audit(self.db, self.wh_id, self.role, action, detail)

    # ── lookups ──
    def role_of(self, b: m.Bin | None) -> str:
        return self.types[b.storage_type_id].role if b and b.storage_type_id in self.types else ""

    def is_storage(self, b: m.Bin | None) -> bool:
        return bool(b) and not b.blocked and self.role_of(b) == "STORAGE"

    def first_bin(self, *roles) -> m.Bin | None:
        cands = [b for b in self.bins.values() if self.role_of(b) in roles]
        return sorted(cands, key=lambda b: (b.y, b.x, b.z, b.id))[0] if cands else None

    def bin_rows(self, bin_id: int):
        return [s for s in self.stock if s.bin_id == bin_id]

    def bin_qty(self, bin_id: int) -> float:
        return sum(s.qty for s in self.bin_rows(bin_id))

    def mat_qty(self, mat_id: int) -> float:
        return sum(s.qty for s in self.stock if s.material_id == mat_id)

    # ── capacity ──
    def bin_load(self, bin_id: int):
        q = w = v = 0.0
        for s in self.bin_rows(bin_id):
            mt = self.mats.get(s.material_id)
            q += s.qty
            w += s.qty * (mt.weight if mt else 0)
            v += s.qty * (mt.volume if mt else 0)
        return q, w, v

    def fit_qty(self, b: m.Bin, mat: m.Material) -> float:
        q, w, v = self.bin_load(b.id)
        caps = []
        if b.max_qty > 0:
            caps.append(b.max_qty - q)
        if b.max_weight > 0:
            caps.append((b.max_weight - w) / mat.weight if mat.weight > 0 else float("inf"))
        if b.max_volume > 0:
            caps.append((b.max_volume - v) / mat.volume if mat.volume > 0 else float("inf"))
        if not caps:
            return float("inf")
        return max(0.0, int(min(caps) * 1000) / 1000)

    def fill_pct(self, b: m.Bin) -> float:
        q, w, v = self.bin_load(b.id)
        p = [x for x in ((q / b.max_qty) if b.max_qty > 0 else None, (w / b.max_weight) if b.max_weight > 0 else None,
                         (v / b.max_volume) if b.max_volume > 0 else None) if x is not None]
        return min(1.0, max(p)) if p else 0.0

    # ── stock movements ──
    def add_stock(self, bin_id: int, mat_id: int, qty: float, batch="", serial="", expiry=None) -> m.Stock:
        batch, serial = batch or "", serial or ""
        if not serial:
            for s in self.stock:
                if s.bin_id == bin_id and s.material_id == mat_id and s.batch == batch and s.serial == "":
                    s.qty += qty
                    return s
        s = m.Stock(warehouse_id=self.wh_id, bin_id=bin_id, material_id=mat_id, qty=qty, batch=batch, serial=serial,
                    expiry=expiry, gr_seq=self._seq)
        self._seq += 1
        self.db.add(s)
        self.db.flush()
        self.stock.append(s)
        return s

    def remove_stock(self, s: m.Stock, qty: float):
        s.qty -= qty
        if s.qty <= 1e-4:
            self.stock.remove(s)
            self.db.delete(s)

    def take_from(self, bin_id: int, mat_id: int, trk: str, qty: float) -> float:
        left = qty
        rows = sorted(self.bin_rows(bin_id), key=lambda s: 0 if (s.batch or s.serial) == (trk or "") else 1)
        for s in [r for r in rows if r.material_id == mat_id]:
            if left <= EPS:
                break
            t = min(left, s.qty)
            self.remove_stock(s, t)
            left -= t
        return qty - left

    def track_split(self, mat: m.Material, trk: str):
        return (trk if mat.tracking == "BATCH" else ""), (trk if mat.tracking == "SERIAL" else "")

    # ── putaway strategy ──
    def find_putaway_bin(self, mat: m.Material, used: dict) -> m.Bin | None:
        def ok(b):
            if not self.is_storage(b):
                return False
            st = self.types[b.storage_type_id]
            if not st.mixed_storage and any(s.material_id != mat.id for s in self.bin_rows(b.id)):
                return False
            return self.fit_qty(b, mat) - used.get(b.id, 0) > 0
        cand = [b for b in self.bins.values() if ok(b)]
        if not cand:
            return None
        fixed = [b for b in cand if b.fixed_material_id == mat.id]
        st = self.cfg.putaway_strategy
        if fixed:  # a bin fixed to this material always wins (as in the prototype)
            return fixed[0]
        if st == "consolidate":
            same = [b for b in cand if any(s.material_id == mat.id for s in self.bin_rows(b.id))]
            if same:
                return max(same, key=lambda b: self.fit_qty(b, mat))
        if st == "capacity":
            return max(cand, key=lambda b: self.fit_qty(b, mat))
        return min(cand, key=lambda b: (self.types[b.storage_type_id].putaway_rank, b.x + b.y + b.z * 2, b.id))

    # ── pick strategy ──
    def pick_sources(self, mat_id: int, qty: float, consumed: dict):
        rows = [s for s in self.stock if s.material_id == mat_id and s.qty > 0 and self.is_storage(self.bins.get(s.bin_id))]
        st = self.cfg.pick_strategy
        if st == "FEFO":
            rows.sort(key=lambda s: (s.expiry or FAR, s.gr_seq))
        elif st == "FIFO":
            rows.sort(key=lambda s: s.gr_seq)
        elif st == "LIFO":
            rows.sort(key=lambda s: -s.gr_seq)
        elif st == "nearest":
            rows.sort(key=lambda s: (lambda b: b.x + b.y + b.z * 2)(self.bins[s.bin_id]))
        elif st == "fixed":
            rows.sort(key=lambda s: (0 if self.bins[s.bin_id].fixed_material_id == mat_id else 1, s.gr_seq))
        if st not in ("nearest", "fixed"):
            rows.sort(key=lambda s: 0 if self.bins[s.bin_id].pick_face else 1)  # stable: pick faces first
        out, need = [], qty
        for r in rows:
            if need <= EPS:
                break
            avail = r.qty - consumed.get(r.id, 0)
            if avail <= EPS:
                continue
            take = min(need, avail)
            consumed[r.id] = consumed.get(r.id, 0) + take
            out.append({"stock": r, "bin_id": r.bin_id, "qty": take, "trk": r.batch or r.serial, "expiry": r.expiry})
            need -= take
        return out, max(0.0, need)

    # ── BOM explosion ──
    @property
    def boms(self):
        if self._boms is None:
            self._boms = {}
            for b in self.db.scalars(select(m.Bom)):
                self._boms[b.parent_material_id] = [(i.material_id, i.qty) for i in
                                                    self.db.scalars(select(m.BomItem).where(m.BomItem.bom_id == b.id))]
        return self._boms

    def explode(self, mat_id: int, qty: float, depth=0, virtual=None):
        virtual = virtual if virtual is not None else {}
        comps = self.boms.get(mat_id)
        have = max(0.0, self.mat_qty(mat_id) - virtual.get(mat_id, 0))
        if not comps or depth > 4:
            return [(mat_id, qty, depth)]
        if have >= qty:
            virtual[mat_id] = virtual.get(mat_id, 0) + qty
            return [(mat_id, qty, depth)]
        out = []
        if have > 0:
            virtual[mat_id] = virtual.get(mat_id, 0) + have
            out.append((mat_id, have, depth))
        for c, q in comps:
            out += self.explode(c, q * (qty - have), depth + 1, virtual)
        return out

    # ── documents & tasks ──
    def work_bin(self, doc_type: str, t: m.WarehouseTask) -> m.Bin | None:
        return self.bins.get(t.dest_bin_id if doc_type == "PUTAWAY" else t.source_bin_id)

    def create_document(self, doc_type: str, tasks: list[dict], *, steps=1, stage_bin_id=None, strategy="", source="",
                        wave_id=None, shortages=(), confirmed=False) -> m.WtDocument:
        prefix = {"PUTAWAY": "PA", "PICK": "PK", "REPLEN": "RP", "REARR": "RA", "XDOCK": "XK"}[doc_type]
        doc = m.WtDocument(warehouse_id=self.wh_id, number=next_number(self.db, self.wh_id, prefix, prefix), type=doc_type,
                           steps=steps, stage_bin_id=stage_bin_id, strategy=strategy, source=source[:100],
                           wave_id=wave_id, status="DONE" if confirmed else "OPEN")
        self.db.add(doc)
        self.db.flush()
        objs = []
        for i, t in enumerate(tasks, 1):
            o = m.WarehouseTask(warehouse_id=self.wh_id, document_id=doc.id, line_no=i,
                                wt_number=next_int(self.db, self.wh_id, "WT"), material_id=t["material_id"], qty=t["qty"],
                                tracking_no=t.get("trk") or "", expiry=t.get("expiry"),
                                source_bin_id=t.get("source_bin_id"), dest_bin_id=t.get("dest_bin_id"),
                                stock_id=t.get("stock_id"), level=t.get("level", 0), orders_ref=t.get("orders", "")[:200],
                                status="CONFIRMED" if confirmed else "OPEN",
                                confirmed_at=utcnow() if confirmed else None)
            self.db.add(o)
            objs.append(o)
        for s in shortages:
            self.db.add(m.DocumentShortage(document_id=doc.id, material_id=s["material_id"], qty=s["qty"], level=s.get("level", 0)))
        self.db.flush()
        if not confirmed:
            self.build_wos(doc, objs)
        return doc

    def tasks_of(self, doc_id: int) -> list[m.WarehouseTask]:
        return list(self.db.scalars(select(m.WarehouseTask).where(m.WarehouseTask.document_id == doc_id)
                                    .order_by(m.WarehouseTask.line_no)))

    # ── warehouse orders: group by activity area, sort along the path, split by max tasks ──
    def area_key(self, b: m.Bin) -> str:
        return str(b.activity_area_id) if b.activity_area_id else f"ST:{b.storage_type_id}"

    def queue_for(self, doc_type: str, key: str) -> int | None:
        aa = int(key) if key.isdigit() else None
        for q in self.db.scalars(select(m.Queue).where(m.Queue.warehouse_id == self.wh_id).order_by(m.Queue.id)):
            if doc_type in (q.task_types or []) and (not q.activity_area_ids or (aa is not None and aa in q.activity_area_ids)):
                return q.id
        return None

    def build_wos(self, doc: m.WtDocument, tasks: list[m.WarehouseTask]):
        groups: dict[str, list] = {}
        for t in tasks:
            b = self.work_bin(doc.type, t)
            if b is None or t.status != "OPEN":
                continue
            groups.setdefault(self.area_key(b), []).append((t, b))
        mx = max(1, self.cfg.wo_max_tasks or 6)
        for key, arr in groups.items():
            serp = False
            if key.isdigit():
                aa = self.db.get(m.ActivityArea, int(key))
                serp = bool(aa and aa.path_sort == "serp")
            arr.sort(key=lambda tb: (tb[1].y, (-tb[1].x if serp and tb[1].y % 2 else tb[1].x), tb[1].z))
            qid = self.queue_for(doc.type, key)
            for i in range(0, len(arr), mx):
                wo = m.WarehouseOrder(warehouse_id=self.wh_id, number=next_number(self.db, self.wh_id, "WO", "WO", 5),
                                      document_id=doc.id, type=doc.type, area_key=key, queue_id=qid, status="OPEN")
                self.db.add(wo)
                self.db.flush()
                for t, _ in arr[i:i + mx]:
                    t.wo_id = wo.id

    # ── confirmation ──
    def confirm_task(self, doc: m.WtDocument, t: m.WarehouseTask):
        if t.status == "CONFIRMED":
            return
        mat = self.mats[t.material_id]
        batch, serial = self.track_split(mat, t.tracking_no)

        def take_source():
            s = next((x for x in self.stock if x.id == t.stock_id), None) if t.stock_id else None
            if s is not None and s.bin_id == t.source_bin_id:
                self.remove_stock(s, min(t.qty, s.qty))
            elif t.source_bin_id:
                self.take_from(t.source_bin_id, t.material_id, t.tracking_no, t.qty)

        if doc.type == "PUTAWAY":
            if doc.steps == 2 and t.source_bin_id:
                self.take_from(t.source_bin_id, t.material_id, t.tracking_no, t.qty)
            self.add_stock(t.dest_bin_id, t.material_id, t.qty, batch, serial, t.expiry)
            self.log("PUTAWAY", f"{t.qty:g} {mat.code} → {self.bins[t.dest_bin_id].code} ({doc.number})")
        elif doc.type in ("REPLEN", "REARR", "XDOCK"):
            take_source()
            self.add_stock(t.dest_bin_id, t.material_id, t.qty, batch, serial, t.expiry)
            self.log(doc.type, f"{t.qty:g} {mat.code}: {self.bins[t.source_bin_id].code} → {self.bins[t.dest_bin_id].code} ({doc.number})")
        else:  # PICK
            take_source()
            if t.dest_bin_id:
                self.add_stock(t.dest_bin_id, t.material_id, t.qty, batch, serial, t.expiry)
            self.log("PICK", f"{t.qty:g} {mat.code} from {self.bins[t.source_bin_id].code} ({doc.number})")
        t.status, t.confirmed_at = "CONFIRMED", utcnow()

    def finish_doc(self, doc: m.WtDocument):
        tasks = self.tasks_of(doc.id)
        self.sync_wos(doc.id, tasks)
        if any(t.status != "CONFIRMED" for t in tasks) or doc.status == "DONE":
            return
        doc.status = "DONE"
        if doc.wave_id:
            wave = self.db.get(m.Wave, doc.wave_id)
            if wave:
                wave.status = "DONE"
            shipped = []
            for o in self.db.scalars(select(m.SalesOrder).where(m.SalesOrder.wave_id == doc.wave_id)):
                o.status = "STAGED" if doc.steps == 2 else "SHIPPED"
                if o.status == "SHIPPED":
                    shipped.append(o)
            if shipped:
                from .transfers import on_source_shipped
                for o in shipped:
                    if o.transfer_id:
                        on_source_shipped(self.db, self, o, self.role)
        if doc.type == "XDOCK":
            for xo in self.db.scalars(select(m.CrossdockOrder).where(m.CrossdockOrder.document_id == doc.id)):
                if xo.status == "IN_XDOCK":
                    xo.status, xo.ready_at = "READY", utcnow()

    def sync_wos(self, doc_id: int, tasks: list[m.WarehouseTask]):
        by_wo: dict[int, list] = {}
        for t in tasks:
            if t.wo_id:
                by_wo.setdefault(t.wo_id, []).append(t)
        for wo_id, ts in by_wo.items():
            wo = self.db.get(m.WarehouseOrder, wo_id)
            if wo and wo.status != "CONFIRMED" and all(t.status == "CONFIRMED" for t in ts):
                wo.status, wo.done_at = "CONFIRMED", utcnow()
                wo.started_at = wo.started_at or wo.done_at
                if wo.resource_id:
                    r = self.db.get(m.Resource, wo.resource_id)
                    if r and r.current_wo_id == wo.id:
                        r.current_wo_id, r.status = None, "AVAILABLE"

    def confirm_tasks(self, task_ids: list[int]) -> int:
        n, docs = 0, {}
        for tid in task_ids:
            t = self.db.get(m.WarehouseTask, tid)
            if not t or t.warehouse_id != self.wh_id or t.status == "CONFIRMED":
                continue
            doc = docs.setdefault(t.document_id, self.db.get(m.WtDocument, t.document_id))
            self.confirm_task(doc, t)
            n += 1
        self.db.flush()
        for doc in docs.values():
            self.finish_doc(doc)
        return n

    # ── resources ──
    def wo_eligible(self, wo: m.WarehouseOrder, r: m.Resource) -> bool:
        if wo.status != "OPEN":
            return False
        if r.queue_ids and wo.queue_id not in r.queue_ids:
            return False
        rt = self.db.get(m.ResourceType, r.resource_type_id) if r.resource_type_id else None
        if rt and rt.max_level > 0:
            for t in self.db.scalars(select(m.WarehouseTask).where(m.WarehouseTask.wo_id == wo.id)):
                for bid in (t.source_bin_id, t.dest_bin_id):
                    if bid and self.bins.get(bid) and self.bins[bid].z > rt.max_level:
                        return False
        return True

    def wo_assign(self, wo: m.WarehouseOrder, r: m.Resource):
        if r.status != "AVAILABLE":
            raise BizError(f"{r.code} is not available (status {r.status})")
        if not self.wo_eligible(wo, r):
            raise BizError(f"{r.code} cannot take {wo.number} (queue or reach level)")
        wo.resource_id, wo.status, wo.started_at = r.id, "IN_PROCESS", utcnow()
        r.current_wo_id, r.status = wo.id, "BUSY"
        self.log("RSRC", f"{wo.number} assigned to {r.code}")

    def wo_release(self, wo: m.WarehouseOrder):
        r = self.db.get(m.Resource, wo.resource_id) if wo.resource_id else None
        if r and r.current_wo_id == wo.id:
            r.current_wo_id, r.status = None, "AVAILABLE"
        wo.resource_id, wo.status, wo.started_at = None, "OPEN", None

    def wo_next(self, r: m.Resource) -> m.WarehouseOrder | None:
        if r.status != "AVAILABLE":
            return None
        for wo in self.db.scalars(select(m.WarehouseOrder).where(m.WarehouseOrder.warehouse_id == self.wh_id,
                                                                 m.WarehouseOrder.status == "OPEN")
                                  .order_by(m.WarehouseOrder.created_at, m.WarehouseOrder.id)):
            if self.wo_eligible(wo, r):
                self.wo_assign(wo, r)
                return wo
        return None

    def wo_confirm(self, wo: m.WarehouseOrder):
        doc = self.db.get(m.WtDocument, wo.document_id)
        ids = [t.id for t in self.db.scalars(select(m.WarehouseTask).where(m.WarehouseTask.wo_id == wo.id,
                                                                           m.WarehouseTask.status == "OPEN"))]
        self.confirm_tasks(ids)
        if wo.status != "CONFIRMED":
            wo.status, wo.done_at = "CONFIRMED", utcnow()
        self.log("WO", f"{wo.number} confirmed ({len(ids)} WTs, {doc.number if doc else ''})")

    # ── inbound ──
    def build_putaway(self, lines: list[dict], source: str) -> m.WtDocument | None:
        cfg = self.cfg
        stage = self.bins.get(cfg.stage_in_bin_id) if cfg.putaway_steps == 2 else None
        if cfg.putaway_steps == 2 and stage is None:
            raise BizError("2-step putaway needs a receiving bin — set it in Strategies")
        tasks, used, short = [], {}, []
        for l in lines:
            mat = self.mats[l["material_id"]]
            need, guard = l["qty"], 0
            while need > EPS and guard < 200:
                guard += 1
                b = self.find_putaway_bin(mat, used)
                if b is None:
                    short.append({"material_id": mat.id, "qty": need})
                    break
                room = self.fit_qty(b, mat) - used.get(b.id, 0)
                if mat.tracking == "SERIAL":
                    room = float(int(room))
                if room <= EPS:
                    used[b.id] = 1e12
                    continue
                take = min(need, room)
                used[b.id] = used.get(b.id, 0) + take
                tasks.append({"material_id": mat.id, "qty": take, "trk": l.get("trk", ""), "expiry": l.get("expiry"),
                              "source_bin_id": stage.id if stage else None, "dest_bin_id": b.id})
                need -= take
        if stage:
            for l in lines:
                mat = self.mats[l["material_id"]]
                self.add_stock(stage.id, mat.id, l["qty"], *self.track_split(mat, l.get("trk", "")), l.get("expiry"))
        return self.create_document("PUTAWAY", tasks, steps=cfg.putaway_steps, stage_bin_id=stage.id if stage else None,
                                    strategy=cfg.putaway_strategy, source=source, shortages=short)

    def opportunistic_split(self, asn: m.Asn, lines: list[dict]) -> list[dict]:
        if not self.cfg.xdock_opportunistic:
            return lines
        out = []
        open_short = list(self.db.scalars(
            select(m.DocumentShortage).join(m.WtDocument, m.WtDocument.id == m.DocumentShortage.document_id)
            .where(m.WtDocument.warehouse_id == self.wh_id, m.WtDocument.type == "PICK")))
        for l in lines:
            left, mat = l["qty"], self.mats[l["material_id"]]
            for s in [x for x in open_short if x.material_id == mat.id and x.qty > EPS]:
                if left <= EPS:
                    break
                doc = self.db.get(m.WtDocument, s.document_id)
                dest = self.bins.get(doc.stage_bin_id) or self.first_bin("SHIPPING")
                if dest is None:
                    continue
                t = min(left, s.qty)
                self.add_stock(dest.id, mat.id, t, *self.track_split(mat, l.get("trk", "")), l.get("expiry"))
                s.qty -= t
                left -= t
                self.db.add(m.XdockEvent(warehouse_id=self.wh_id, asn_number=asn.number, material_id=mat.id, qty=t,
                                         to_bin_id=dest.id, pick_doc_number=doc.number, tracking_no=l.get("trk", "")))
                self.log("XDOCK", f"{t:g} {mat.code}: {asn.number} → {dest.code} for {doc.number} backorder")
                if s.qty <= EPS:
                    self.db.delete(s)
            if left > EPS:
                out.append({**l, "qty": left})
        return out

    def receive_asn(self, asn: m.Asn):
        if asn.status != "OPEN":
            raise BizError(f"{asn.number} is already {asn.status}")
        if asn.hub_crossdock:
            from .transfers import hub_receive
            xo = hub_receive(self.db, self, asn, self.role)
            return {"crossdock_order": xo.number, "document": None}
        lines = [{"material_id": l.material_id, "qty": l.qty, "trk": l.tracking_no, "expiry": l.expiry}
                 for l in self.db.scalars(select(m.AsnLine).where(m.AsnLine.asn_id == asn.id))]
        if self.cfg.putaway_steps == 2 and self.bins.get(self.cfg.stage_in_bin_id) is None:
            raise BizError("2-step putaway needs a receiving bin — set it in Strategies")
        rest = self.opportunistic_split(asn, lines)
        xq = sum(l["qty"] for l in lines) - sum(l["qty"] for l in rest)
        doc = self.build_putaway(rest, f"ASN {asn.number}") if rest else None
        asn.status = "RECEIVED"
        self.log("RECEIVE", f"{asn.number} received" + (f" → {doc.number}" if doc else "") + (f" ({xq:g} cross-docked)" if xq else ""))
        if asn.transfer_id:
            from .transfers import on_dest_received
            on_dest_received(self.db, asn, doc)
        return {"document": doc.number if doc else None, "document_id": doc.id if doc else None, "crossdocked_qty": xq}

    # ── outbound ──
    def create_wave(self, order_ids: list[int]) -> m.WtDocument:
        cfg = self.cfg
        stage = self.bins.get(cfg.stage_out_bin_id) if cfg.pick_steps == 2 else None
        if cfg.pick_steps == 2 and stage is None:
            raise BizError("2-step picking needs a staging bin — set it in Strategies")
        orders = [o for o in (self.db.get(m.SalesOrder, i) for i in order_ids)
                  if o and o.warehouse_id == self.wh_id and o.status == "OPEN"]
        if not orders:
            raise BizError("Select at least one open order")
        demand, virtual = {}, {}
        for o in orders:
            for l in self.db.scalars(select(m.SalesOrderLine).where(m.SalesOrderLine.order_id == o.id)):
                parts = self.explode(l.material_id, l.qty, 0, virtual) if cfg.explode_bom else [(l.material_id, l.qty, 0)]
                for mid, q, lvl in parts:
                    d = demand.setdefault((mid, lvl), {"qty": 0.0, "orders": set()})
                    d["qty"] += q
                    d["orders"].add(o.number)
        tasks, short, consumed = [], [], {}
        for (mid, lvl), d in demand.items():
            src, sh = self.pick_sources(mid, d["qty"], consumed)
            for s in src:
                tasks.append({"material_id": mid, "qty": s["qty"], "trk": s["trk"], "expiry": s["expiry"],
                              "source_bin_id": s["bin_id"], "dest_bin_id": stage.id if stage else None,
                              "stock_id": s["stock"].id, "level": lvl, "orders": ", ".join(sorted(d["orders"]))})
            if sh > EPS:
                short.append({"material_id": mid, "qty": sh, "level": lvl})
        tasks.sort(key=lambda t: (self.bins[t["source_bin_id"]].z, self.bins[t["source_bin_id"]].y, self.bins[t["source_bin_id"]].x))
        wave = m.Wave(warehouse_id=self.wh_id, number=next_number(self.db, self.wh_id, "WV", "WV"))
        self.db.add(wave)
        self.db.flush()
        doc = self.create_document("PICK", tasks, steps=cfg.pick_steps, stage_bin_id=stage.id if stage else None,
                                   strategy=cfg.pick_strategy, source=f"Wave {wave.number}", wave_id=wave.id, shortages=short)
        for o in orders:
            o.status, o.wave_id = "WAVED", wave.id
        self.log("WAVE", f"{wave.number} released — {len(orders)} orders, {len(tasks)} WTs ({doc.number})")
        return doc

    def pick_and_ship(self, order: m.SalesOrder) -> m.WtDocument:
        """Immediate pick + goods issue (used for stock transfers)."""
        tasks, short, consumed = [], [], {}
        for l in self.db.scalars(select(m.SalesOrderLine).where(m.SalesOrderLine.order_id == order.id)):
            src, sh = self.pick_sources(l.material_id, l.qty, consumed)
            if sh > EPS:
                short.append(f"{self.mats[l.material_id].code} × {sh:g}")
            tasks += [{"material_id": l.material_id, "qty": s["qty"], "trk": s["trk"], "expiry": s["expiry"],
                       "source_bin_id": s["bin_id"], "stock_id": s["stock"].id, "orders": order.number} for s in src]
        if short:
            raise BizError("Not enough stock: " + ", ".join(short))
        for t in tasks:
            s = next(x for x in self.stock if x.id == t["stock_id"])
            self.remove_stock(s, t["qty"])
        wave = m.Wave(warehouse_id=self.wh_id, number=next_number(self.db, self.wh_id, "WV", "WV"), status="DONE")
        self.db.add(wave)
        self.db.flush()
        doc = self.create_document("PICK", tasks, strategy=self.cfg.pick_strategy, source=f"Wave {wave.number} (transfer)",
                                   wave_id=wave.id, confirmed=True)
        order.status, order.wave_id = "SHIPPED", wave.id
        self.log("PICK", f"{order.number} picked & shipped — {len(tasks)} WTs ({doc.number})")
        return doc
