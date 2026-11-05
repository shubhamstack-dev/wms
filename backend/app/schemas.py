"""Request bodies (validation lives here; responses are plain dicts built from the ORM rows)."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from .services.gst import check_gstin, PAN_RE, PIN_RE

TaskType = Literal["PICK", "PUTAWAY", "REPLEN", "REARR", "XDOCK"]


class Coded(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = ""

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def _default_name(self):
        if not self.name:
            self.name = self.code
        return self


# ── enterprise ──
class CompanyIn(Coded):
    legal_name: str = ""
    pan: str = ""
    cin: str = ""
    currency: str = "INR"
    country: str = "IN"

    @field_validator("pan")
    @classmethod
    def _pan(cls, v):
        v = v.strip().upper()
        if v and not PAN_RE.match(v):
            raise ValueError("PAN format: 5 letters, 4 digits, 1 letter (e.g. AABCB1234F)")
        return v


class PlantIn(Coded):
    company_id: int
    city: str = ""


class StorageLocationIn(Coded):
    plant_id: int
    warehouse_id: int | None = None


class WarehouseIn(Coded):
    type: Literal["DC", "PLANT", "XD"] = "DC"
    trade_name: str = ""
    addr_line1: str = ""
    addr_line2: str = ""
    city: str = ""
    district: str = ""
    state_code: str = ""
    pin: str = ""
    country: str = "India"
    gstin: str = ""
    contact: str = ""
    phone: str = ""
    email: str = ""

    @field_validator("pin")
    @classmethod
    def _pin(cls, v):
        v = v.strip()
        if v and not PIN_RE.match(v):
            raise ValueError("PIN code must be 6 digits")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = v.strip()
        if v and ("@" not in v or "." not in v.split("@")[-1]):
            raise ValueError("Email looks invalid")
        return v

    @model_validator(mode="after")
    def _gst(self):
        g = check_gstin(self.gstin)
        if not g["ok"] and not g.get("empty"):
            raise ValueError("GSTIN invalid — " + g["msg"])
        if g["ok"]:
            self.gstin = g["gstin"]
            if self.state_code and self.state_code != g["state"]:
                raise ValueError(f"GSTIN is registered in state {g['state']} but the address state is {self.state_code}")
            self.state_code = self.state_code or g["state"]
        return self


class WarehouseCreate(WarehouseIn):
    copy_from_id: int | None = None
    copy_bins: bool = False
    plant_id: int | None = None
    sloc_code: str = ""


# ── warehouse organisation ──
class StorageTypeIn(Coded):
    role: Literal["STORAGE", "RECEIVING", "QC", "STAGING", "SHIPPING"] = "STORAGE"
    putaway_rank: int = 1
    pick_rank: int = 1
    mixed_storage: bool = True


class SectionIn(Coded):
    storage_type_id: int


class BinTypeIn(Coded):
    max_qty: float = Field(0, ge=0)
    max_weight: float = Field(0, ge=0)
    max_volume: float = Field(0, ge=0)


class ActivityAreaIn(Coded):
    activity: Literal["ALL", "PICK", "PTWY", "INVE"] = "ALL"
    path_sort: Literal["serp", "aisle"] = "serp"


class QueueIn(Coded):
    activity_area_ids: list[int] = []
    task_types: list[TaskType] = []


class ResourceTypeIn(Coded):
    max_level: int = Field(0, ge=0)


class ResourceIn(Coded):
    resource_type_id: int | None = None
    queue_ids: list[int] = []


class WorkCenterIn(Coded):
    kind: Literal["PACK", "VAS", "QUAL", "DECO"] = "PACK"
    bin_id: int | None = None


class DoorIn(Coded):
    direction: Literal["IN", "OUT", "BOTH"] = "IN"
    bin_id: int | None = None


class ConfigIn(BaseModel):
    putaway_steps: Literal[1, 2] | None = None
    putaway_strategy: Literal["nearest", "fixed", "consolidate", "capacity"] | None = None
    pick_steps: Literal[1, 2] | None = None
    pick_strategy: Literal["FEFO", "FIFO", "LIFO", "nearest", "fixed"] | None = None
    stage_in_bin_id: int | None = None
    stage_out_bin_id: int | None = None
    explode_bom: bool | None = None
    xdock_opportunistic: bool | None = None
    xd_in_bin_id: int | None = None
    xd_out_bin_id: int | None = None
    wo_max_tasks: int | None = Field(None, ge=1, le=100)


# ── layout ──
class RackIn(Coded):
    storage_type_id: int
    section_id: int | None = None
    bin_type_id: int | None = None
    activity_area_id: int | None = None
    pick_face: bool = False
    x1: int = Field(0, ge=0)
    y1: int = Field(0, ge=0)
    x2: int = Field(7, ge=0)
    y2: int = Field(0, ge=0)
    aisle_from: int = 1
    aisle_to: int = 1
    aisle_gap: int = Field(1, ge=1)
    pos_from: int = 1
    pos_step: int = Field(1, ge=1)
    level_from: int = 1
    level_to: int = 3
    pattern: str = "{ST}-{A}-{P}-{L}"
    pad: int = Field(2, ge=1, le=5)

    @model_validator(mode="after")
    def _ranges(self):
        self.aisle_to = max(self.aisle_from, self.aisle_to)
        self.level_to = max(self.level_from, self.level_to)
        return self


class DrawIn(BaseModel):
    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    level: int = 1
    levels: int = Field(1, ge=1, le=9)
    storage_type_id: int
    section_id: int | None = None
    bin_type_id: int | None = None
    activity_area_id: int | None = None
    prefix: str = ""
    pick_face: bool = False


class BulkAssignIn(BaseModel):
    """None = keep, 0 = clear."""
    bin_ids: list[int]
    all_levels: bool = False
    storage_type_id: int | None = None
    section_id: int | None = None
    bin_type_id: int | None = None
    activity_area_id: int | None = None
    pick_face: bool | None = None
    blocked: bool | None = None


class BinPatch(BaseModel):
    max_qty: float | None = Field(None, ge=0)
    max_weight: float | None = Field(None, ge=0)
    max_volume: float | None = Field(None, ge=0)
    pick_face: bool | None = None
    min_qty: float | None = Field(None, ge=0)
    replen_to: float | None = Field(None, ge=0)
    fixed_material_id: int | None = None
    blocked: bool | None = None


class IdsIn(BaseModel):
    ids: list[int]


# ── materials ──
class MaterialIn(Coded):
    uom: str = "EA"
    type: Literal["FG", "SFG", "RM", "PACK"] = "FG"
    tracking: Literal["NONE", "BATCH", "SERIAL"] = "NONE"
    weight: float = Field(0, ge=0)
    volume: float = Field(0, ge=0)


class BomComponent(BaseModel):
    material_id: int
    qty: float = Field(gt=0)


class BomIn(BaseModel):
    components: list[BomComponent]


# ── documents ──
class LineIn(BaseModel):
    material_id: int
    qty: float = Field(gt=0)
    trk: str = ""
    expiry: date | None = None


class AsnIn(BaseModel):
    vendor: str = ""
    eta: date | None = None
    lines: list[LineIn] = Field(min_length=1)


class OrderLineIn(BaseModel):
    material_id: int
    qty: float = Field(gt=0)


class OrderIn(BaseModel):
    customer: str = ""
    order_date: date | None = None
    lines: list[OrderLineIn] = Field(min_length=1)


class WaveIn(BaseModel):
    order_ids: list[int] = Field(min_length=1)


class AssignIn(BaseModel):
    resource_id: int


class XdOrderIn(BaseModel):
    from_party: str = ""
    to_party: str = ""
    lines: list[LineIn] = Field(min_length=1)


class TransferIn(BaseModel):
    from_wh_id: int
    via_wh_id: int | None = None
    to_wh_id: int
    lines: list[OrderLineIn] = Field(min_length=1)
