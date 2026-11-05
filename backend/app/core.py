"""Shared helpers: roles, business errors, serialisation, numbering, audit."""
from datetime import date, datetime
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models as m

# ── roles (header-based for now; swap for real authentication — see README) ──
ROLES = {
    "OPERATOR": {"confirm", "count", "move"},
    "SUPERVISOR": {"confirm", "count", "move", "create", "release", "adjust", "master"},
    "ADMIN": {"confirm", "count", "move", "create", "release", "adjust", "master", "config", "setup", "reset"},
}


def get_role(x_role: str = Header(default="OPERATOR")) -> str:
    return x_role.upper() if x_role.upper() in ROLES else "OPERATOR"


def require(role: str, action: str):
    if action not in ROLES.get(role, set()):
        raise HTTPException(403, f"Role {role} is not allowed to '{action}'")


class BizError(Exception):
    """A business-rule violation — returned to the client as HTTP 400 with a readable message."""


def to_dict(obj) -> dict:
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def rows(objs) -> list[dict]:
    return [to_dict(o) for o in objs]


def next_number(db: Session, wh_id: int, obj: str, prefix: str, width: int = 4) -> str:
    n = next_int(db, wh_id, obj)
    return f"{prefix}-{n:0{width}d}"


def next_int(db: Session, wh_id: int, obj: str) -> int:
    nr = db.execute(select(m.NumberRange).where(m.NumberRange.warehouse_id == wh_id, m.NumberRange.object == obj)
                    .with_for_update()).scalar_one_or_none()
    if nr is None:
        nr = m.NumberRange(warehouse_id=wh_id, object=obj, last_no=0)
        db.add(nr)
    nr.last_no += 1
    db.flush()
    return nr.last_no


def audit(db: Session, wh_id: int | None, role: str, action: str, detail: str):
    db.add(m.AuditLog(warehouse_id=wh_id, role=role, action=action, detail=detail[:500]))


def get_or_404(db: Session, model, id_: int, wh_id: int | None = None):
    obj = db.get(model, id_)
    if obj is None or (wh_id is not None and getattr(obj, "warehouse_id", wh_id) != wh_id):
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


def utcnow():
    """Naive UTC timestamp (MySQL DATETIME has no time zone)."""
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)
