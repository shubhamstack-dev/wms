"""ORM models — single source of truth for the MySQL schema (database/schema.sql is generated from these)."""
from datetime import datetime, date
from sqlalchemy import (BigInteger, Integer, String, Boolean, Date, DateTime, Numeric, JSON, ForeignKey,
                        UniqueConstraint, Index, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ID = BigInteger().with_variant(Integer, "sqlite")   # BIGINT on MySQL, INTEGER (rowid) on SQLite for tests
QTY = Numeric(18, 4, asdecimal=False)   # exact DECIMAL in MySQL, float in Python


class Base(DeclarativeBase):
    pass


def pk():
    return mapped_column(ID, primary_key=True, autoincrement=True)


def fk(target, nullable=False, ondelete=None):
    return mapped_column(ID, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


def wh_fk():
    return fk("warehouse.id", ondelete="CASCADE")


# ───────────────────────── Enterprise structure ─────────────────────────
class Company(Base):
    __tablename__ = "company"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    legal_name: Mapped[str] = mapped_column(String(200), default="")
    pan: Mapped[str] = mapped_column(String(10), default="")
    cin: Mapped[str] = mapped_column(String(21), default="")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    country: Mapped[str] = mapped_column(String(2), default="IN")


class Plant(Base):
    __tablename__ = "plant"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    company_id: Mapped[int] = fk("company.id")
    city: Mapped[str] = mapped_column(String(100), default="")


class Warehouse(Base):
    """Warehouse number. Address + GSTIN are captured master data only (passed to other systems, no billing)."""
    __tablename__ = "warehouse"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(8), default="DC")          # DC | PLANT | XD
    trade_name: Mapped[str] = mapped_column(String(150), default="")
    addr_line1: Mapped[str] = mapped_column(String(200), default="")
    addr_line2: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    district: Mapped[str] = mapped_column(String(100), default="")
    state_code: Mapped[str] = mapped_column(String(2), default="")
    pin: Mapped[str] = mapped_column(String(6), default="")
    country: Mapped[str] = mapped_column(String(60), default="India")
    gstin: Mapped[str] = mapped_column(String(15), default="", index=True)
    contact: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(150), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StorageLocation(Base):
    __tablename__ = "storage_location"
    __table_args__ = (UniqueConstraint("plant_id", "code"),)
    id: Mapped[int] = pk()
    plant_id: Mapped[int] = fk("plant.id", ondelete="CASCADE")
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), default="")
    warehouse_id: Mapped[int | None] = fk("warehouse.id", nullable=True, ondelete="SET NULL")


class WarehouseConfig(Base):
    __tablename__ = "warehouse_config"
    warehouse_id: Mapped[int] = mapped_column(ID, ForeignKey("warehouse.id", ondelete="CASCADE"), primary_key=True)
    putaway_steps: Mapped[int] = mapped_column(Integer, default=1)
    putaway_strategy: Mapped[str] = mapped_column(String(12), default="nearest")   # nearest|fixed|consolidate|capacity
    pick_steps: Mapped[int] = mapped_column(Integer, default=1)
    pick_strategy: Mapped[str] = mapped_column(String(8), default="FEFO")           # FEFO|FIFO|LIFO|nearest|fixed
    stage_in_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    stage_out_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    explode_bom: Mapped[bool] = mapped_column(Boolean, default=True)
    xdock_opportunistic: Mapped[bool] = mapped_column(Boolean, default=False)
    xd_in_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    xd_out_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    wo_max_tasks: Mapped[int] = mapped_column(Integer, default=6)


# ───────────────────────── Warehouse organisation ─────────────────────────
class StorageType(Base):
    __tablename__ = "storage_type"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(10), default="STORAGE")  # STORAGE|RECEIVING|QC|STAGING|SHIPPING
    putaway_rank: Mapped[int] = mapped_column(Integer, default=1)
    pick_rank: Mapped[int] = mapped_column(Integer, default=1)
    mixed_storage: Mapped[bool] = mapped_column(Boolean, default=True)


class StorageSection(Base):
    __tablename__ = "storage_section"
    __table_args__ = (UniqueConstraint("storage_type_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    storage_type_id: Mapped[int] = fk("storage_type.id", ondelete="CASCADE")
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), default="")


class BinType(Base):
    __tablename__ = "bin_type"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), default="")
    max_qty: Mapped[float] = mapped_column(QTY, default=0)
    max_weight: Mapped[float] = mapped_column(QTY, default=0)
    max_volume: Mapped[float] = mapped_column(QTY, default=0)


class ActivityArea(Base):
    __tablename__ = "activity_area"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), default="")
    activity: Mapped[str] = mapped_column(String(4), default="ALL")
    path_sort: Mapped[str] = mapped_column(String(6), default="serp")   # serp|aisle


class Queue(Base):
    __tablename__ = "queue"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(100), default="")
    activity_area_ids: Mapped[list] = mapped_column(JSON, default=list)   # empty = all areas
    task_types: Mapped[list] = mapped_column(JSON, default=list)          # PICK|PUTAWAY|REPLEN|REARR|XDOCK


class ResourceType(Base):
    __tablename__ = "resource_type"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), default="")
    max_level: Mapped[int] = mapped_column(Integer, default=0)            # 0 = unlimited


class Resource(Base):
    __tablename__ = "resource"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100), default="")
    resource_type_id: Mapped[int | None] = fk("resource_type.id", nullable=True, ondelete="SET NULL")
    queue_ids: Mapped[list] = mapped_column(JSON, default=list)           # empty = all queues
    status: Mapped[str] = mapped_column(String(10), default="LOGGED_OFF") # LOGGED_OFF|AVAILABLE|BUSY
    current_wo_id: Mapped[int | None] = mapped_column(ID, nullable=True)


class WorkCenter(Base):
    __tablename__ = "work_center"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(100), default="")
    kind: Mapped[str] = mapped_column(String(4), default="PACK")
    bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)


class Door(Base):
    __tablename__ = "door"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(100), default="")
    direction: Mapped[str] = mapped_column(String(4), default="IN")     # IN|OUT|BOTH
    bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)


class Rack(Base):
    """Bin structure: start point → end point, aisles, positions, levels, code pattern."""
    __tablename__ = "rack"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100), default="")
    storage_type_id: Mapped[int] = fk("storage_type.id")
    section_id: Mapped[int | None] = fk("storage_section.id", nullable=True, ondelete="SET NULL")
    bin_type_id: Mapped[int | None] = fk("bin_type.id", nullable=True, ondelete="SET NULL")
    activity_area_id: Mapped[int | None] = fk("activity_area.id", nullable=True, ondelete="SET NULL")
    pick_face: Mapped[bool] = mapped_column(Boolean, default=False)
    x1: Mapped[int] = mapped_column(Integer, default=0)
    y1: Mapped[int] = mapped_column(Integer, default=0)
    x2: Mapped[int] = mapped_column(Integer, default=7)
    y2: Mapped[int] = mapped_column(Integer, default=0)
    aisle_from: Mapped[int] = mapped_column(Integer, default=1)
    aisle_to: Mapped[int] = mapped_column(Integer, default=1)
    aisle_gap: Mapped[int] = mapped_column(Integer, default=1)
    pos_from: Mapped[int] = mapped_column(Integer, default=1)
    pos_step: Mapped[int] = mapped_column(Integer, default=1)
    level_from: Mapped[int] = mapped_column(Integer, default=1)
    level_to: Mapped[int] = mapped_column(Integer, default=3)
    pattern: Mapped[str] = mapped_column(String(60), default="{ST}-{A}-{P}-{L}")
    pad: Mapped[int] = mapped_column(Integer, default=2)


class Material(Base):
    """Global material master shared by all warehouses."""
    __tablename__ = "material"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(150), default="")
    uom: Mapped[str] = mapped_column(String(5), default="EA")
    type: Mapped[str] = mapped_column(String(5), default="FG")           # FG|SFG|RM|PACK
    tracking: Mapped[str] = mapped_column(String(6), default="NONE")     # NONE|BATCH|SERIAL
    weight: Mapped[float] = mapped_column(QTY, default=0)
    volume: Mapped[float] = mapped_column(QTY, default=0)


class Bin(Base):
    __tablename__ = "bin"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"), UniqueConstraint("warehouse_id", "x", "y", "z"))
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    code: Mapped[str] = mapped_column(String(40))
    storage_type_id: Mapped[int] = fk("storage_type.id")
    section_id: Mapped[int | None] = fk("storage_section.id", nullable=True, ondelete="SET NULL")
    bin_type_id: Mapped[int | None] = fk("bin_type.id", nullable=True, ondelete="SET NULL")
    activity_area_id: Mapped[int | None] = fk("activity_area.id", nullable=True, ondelete="SET NULL")
    rack_id: Mapped[int | None] = fk("rack.id", nullable=True, ondelete="SET NULL")
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    z: Mapped[int] = mapped_column(Integer, default=1)
    max_qty: Mapped[float] = mapped_column(QTY, default=0)
    max_weight: Mapped[float] = mapped_column(QTY, default=0)
    max_volume: Mapped[float] = mapped_column(QTY, default=0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    pick_face: Mapped[bool] = mapped_column(Boolean, default=False)
    min_qty: Mapped[float] = mapped_column(QTY, default=0)
    replen_to: Mapped[float] = mapped_column(QTY, default=0)
    fixed_material_id: Mapped[int | None] = fk("material.id", nullable=True, ondelete="SET NULL")


class Bom(Base):
    __tablename__ = "bom"
    id: Mapped[int] = pk()
    parent_material_id: Mapped[int] = mapped_column(ID, ForeignKey("material.id", ondelete="CASCADE"), unique=True)


class BomItem(Base):
    __tablename__ = "bom_item"
    id: Mapped[int] = pk()
    bom_id: Mapped[int] = fk("bom.id", ondelete="CASCADE")
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY, default=1)


class Stock(Base):
    __tablename__ = "stock"
    __table_args__ = (Index("ix_stock_wh_mat", "warehouse_id", "material_id"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    bin_id: Mapped[int] = fk("bin.id")
    material_id: Mapped[int] = fk("material.id")
    batch: Mapped[str] = mapped_column(String(40), default="")
    serial: Mapped[str] = mapped_column(String(40), default="")
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty: Mapped[float] = mapped_column(QTY, default=0)
    gr_seq: Mapped[int] = mapped_column(ID, default=0)   # goods-receipt sequence for FIFO/LIFO


# ───────────────────────── Inbound / outbound ─────────────────────────
class Asn(Base):
    __tablename__ = "asn"
    __table_args__ = (UniqueConstraint("warehouse_id", "number"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    number: Mapped[str] = mapped_column(String(20))
    vendor: Mapped[str] = mapped_column(String(150), default="")
    eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OPEN")     # OPEN|RECEIVED
    transfer_id: Mapped[int | None] = mapped_column(ID, nullable=True, index=True)
    hub_crossdock: Mapped[bool] = mapped_column(Boolean, default=False)


class AsnLine(Base):
    __tablename__ = "asn_line"
    id: Mapped[int] = pk()
    asn_id: Mapped[int] = fk("asn.id", ondelete="CASCADE")
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)
    tracking_no: Mapped[str] = mapped_column(String(40), default="")
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)


class Wave(Base):
    __tablename__ = "wave"
    __table_args__ = (UniqueConstraint("warehouse_id", "number"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    number: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SalesOrder(Base):
    __tablename__ = "sales_order"
    __table_args__ = (UniqueConstraint("warehouse_id", "number"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    number: Mapped[str] = mapped_column(String(20))
    customer: Mapped[str] = mapped_column(String(150), default="")
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OPEN")     # OPEN|WAVED|STAGED|SHIPPED
    wave_id: Mapped[int | None] = fk("wave.id", nullable=True, ondelete="SET NULL")
    transfer_id: Mapped[int | None] = mapped_column(ID, nullable=True, index=True)


class SalesOrderLine(Base):
    __tablename__ = "sales_order_line"
    id: Mapped[int] = pk()
    order_id: Mapped[int] = fk("sales_order.id", ondelete="CASCADE")
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)


# ───────────────────────── Execution: documents, WTs, WOs ─────────────────────────
class WtDocument(Base):
    __tablename__ = "wt_document"
    __table_args__ = (UniqueConstraint("warehouse_id", "number"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    number: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(8))                        # PUTAWAY|PICK|REPLEN|REARR|XDOCK
    steps: Mapped[int] = mapped_column(Integer, default=1)
    stage_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    strategy: Mapped[str] = mapped_column(String(20), default="")
    source: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(10), default="OPEN")     # OPEN|DONE
    wave_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentShortage(Base):
    __tablename__ = "document_shortage"
    id: Mapped[int] = pk()
    document_id: Mapped[int] = fk("wt_document.id", ondelete="CASCADE")
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)
    level: Mapped[int] = mapped_column(Integer, default=0)


class WarehouseOrder(Base):
    __tablename__ = "warehouse_order"
    __table_args__ = (UniqueConstraint("warehouse_id", "number"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    number: Mapped[str] = mapped_column(String(20))
    document_id: Mapped[int] = fk("wt_document.id", ondelete="CASCADE")
    type: Mapped[str] = mapped_column(String(8))
    area_key: Mapped[str] = mapped_column(String(30))                    # activity area id, or "ST:<storage type id>"
    queue_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    resource_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")     # OPEN|IN_PROCESS|CONFIRMED
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WarehouseTask(Base):
    __tablename__ = "warehouse_task"
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    document_id: Mapped[int] = fk("wt_document.id", ondelete="CASCADE")
    line_no: Mapped[int] = mapped_column(Integer)
    wt_number: Mapped[int] = mapped_column(ID)
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)
    tracking_no: Mapped[str] = mapped_column(String(40), default="")
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    dest_bin_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    stock_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    orders_ref: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(10), default="OPEN")     # OPEN|CONFIRMED
    wo_id: Mapped[int | None] = fk("warehouse_order.id", nullable=True, ondelete="SET NULL")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ───────────────────────── Cross-docking & transfers ─────────────────────────
class CrossdockOrder(Base):
    __tablename__ = "crossdock_order"
    __table_args__ = (UniqueConstraint("warehouse_id", "number"),)
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    number: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(4), default="PXD")          # PXD (planned) | TCD (transport)
    from_party: Mapped[str] = mapped_column(String(150), default="")
    to_party: Mapped[str] = mapped_column(String(150), default="")
    status: Mapped[str] = mapped_column(String(10), default="PLANNED")  # PLANNED|IN_XDOCK|READY|SHIPPED
    document_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    transfer_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CrossdockOrderLine(Base):
    __tablename__ = "crossdock_order_line"
    id: Mapped[int] = pk()
    order_id: Mapped[int] = fk("crossdock_order.id", ondelete="CASCADE")
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)
    tracking_no: Mapped[str] = mapped_column(String(40), default="")
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)


class XdockEvent(Base):
    """Opportunistic cross-dock: receipt diverted to fill a backorder."""
    __tablename__ = "xdock_event"
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int] = wh_fk()
    asn_number: Mapped[str] = mapped_column(String(20))
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)
    to_bin_id: Mapped[int] = mapped_column(ID)
    pick_doc_number: Mapped[str] = mapped_column(String(20))
    tracking_no: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StockTransfer(Base):
    __tablename__ = "stock_transfer"
    id: Mapped[int] = pk()
    number: Mapped[str] = mapped_column(String(20), unique=True)
    from_wh_id: Mapped[int] = fk("warehouse.id")
    via_wh_id: Mapped[int | None] = fk("warehouse.id", nullable=True)
    to_wh_id: Mapped[int] = fk("warehouse.id")
    status: Mapped[str] = mapped_column(String(16), default="CREATED")
    # CREATED|RELEASED|TO_HUB|AT_HUB|IN_TRANSIT|COMPLETED
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_order_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    hub_asn_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    hub_xd_id: Mapped[int | None] = mapped_column(ID, nullable=True)
    dest_asn_id: Mapped[int | None] = mapped_column(ID, nullable=True)


class StockTransferLine(Base):
    __tablename__ = "stock_transfer_line"
    id: Mapped[int] = pk()
    transfer_id: Mapped[int] = fk("stock_transfer.id", ondelete="CASCADE")
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)


class StockTransferShipped(Base):
    __tablename__ = "stock_transfer_shipped"
    id: Mapped[int] = pk()
    transfer_id: Mapped[int] = fk("stock_transfer.id", ondelete="CASCADE")
    leg: Mapped[int] = mapped_column(Integer, default=1)
    material_id: Mapped[int] = fk("material.id")
    qty: Mapped[float] = mapped_column(QTY)
    tracking_no: Mapped[str] = mapped_column(String(40), default="")
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)


class StockTransferEvent(Base):
    __tablename__ = "stock_transfer_event"
    id: Mapped[int] = pk()
    transfer_id: Mapped[int] = fk("stock_transfer.id", ondelete="CASCADE")
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    message: Mapped[str] = mapped_column(String(300))


# ───────────────────────── Housekeeping ─────────────────────────
class NumberRange(Base):
    __tablename__ = "number_range"
    warehouse_id: Mapped[int] = mapped_column(ID, primary_key=True)     # 0 = enterprise-wide
    object: Mapped[str] = mapped_column(String(10), primary_key=True)
    last_no: Mapped[int] = mapped_column(ID, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = pk()
    warehouse_id: Mapped[int | None] = mapped_column(ID, nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    role: Mapped[str] = mapped_column(String(12), default="")
    action: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(String(500), default="")
