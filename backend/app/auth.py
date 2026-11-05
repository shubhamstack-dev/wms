"""Users, passwords and login tokens.

Users live in their own table (app_user) on a separate metadata, so "Load demo",
legacy import with replace, and `python -m app.clear_data` never delete them.
Passwords: PBKDF2-SHA256 (standard library). Tokens: HMAC-signed, expire after AUTH_HOURS.
Logging out = the browser forgets its token.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, DateTime, Integer, String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import AUTH_HOURS, AUTH_SECRET
from .db import get_db, engine

ROLE_NAMES = ("OPERATOR", "SUPERVISOR", "ADMIN")


class AuthBase(DeclarativeBase):
    pass


class AppUser(AuthBase):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(12), default="OPERATOR")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def create_tables():
    AuthBase.metadata.create_all(engine)


# ── passwords ──
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 260_000)
    return f"pbkdf2_sha256$260000${salt}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, rounds, salt, want = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(dk.hex(), want)
    except ValueError:
        return False


# ── tokens ──
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _sign(body: str) -> str:
    return _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())


def make_token(user: AppUser) -> str:
    body = _b64(json.dumps({"uid": user.id, "exp": int(time.time() + AUTH_HOURS * 3600)}).encode())
    return f"{body}.{_sign(body)}"


def read_token(token: str) -> int | None:
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return int(data["uid"]) if data["exp"] > time.time() else None
    except (ValueError, KeyError, TypeError):
        return None


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> AppUser:
    """Every /api route except health and auth/* depends on this."""
    scheme, _, token = authorization.partition(" ")
    uid = read_token(token) if scheme.lower() == "bearer" else None
    user = db.get(AppUser, uid) if uid else None
    if user is None or not user.active:
        raise HTTPException(401, "Please log in")
    return user


def public(u: AppUser) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "active": u.active}


# ── API ──
r = APIRouter(tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def _clean(cls, v):
        return v.strip().lower()


class NewUser(Credentials):
    password: str = Field(min_length=8, max_length=200)
    role: str = "OPERATOR"

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ROLE_NAMES:
            raise ValueError("Role must be OPERATOR, SUPERVISOR or ADMIN")
        return v


class UserUpdate(BaseModel):
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v is not None and v not in ROLE_NAMES:
            raise ValueError("Role must be OPERATOR, SUPERVISOR or ADMIN")
        return v


def _no_users(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(AppUser)) == 0


@r.get("/auth/status")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": _no_users(db)}


@r.post("/auth/setup")
def setup(body: Credentials, db: Session = Depends(get_db)):
    """Creates the first administrator. Works only while there are no users at all."""
    if not _no_users(db):
        raise HTTPException(409, "An administrator already exists. Please log in.")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    u = AppUser(username=body.username, password_hash=hash_password(body.password), role="ADMIN", active=True)
    db.add(u)
    db.commit()
    return {"token": make_token(u), "user": public(u)}


@r.post("/auth/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    u = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if u is None or not u.active or not check_password(body.password, u.password_hash):
        time.sleep(1)   # slows down password guessing
        raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(u), "user": public(u)}


@r.get("/auth/me")
def me(user: AppUser = Depends(current_user)):
    return public(user)


@r.post("/auth/change-password")
def change_password(body: dict, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    old, new = str(body.get("old_password", "")), str(body.get("new_password", ""))
    if not check_password(old, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    if len(new) < 8:
        raise HTTPException(422, "New password must be at least 8 characters")
    db.get(AppUser, user.id).password_hash = hash_password(new)
    db.commit()
    return {"ok": True}


def _admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != "ADMIN":
        raise HTTPException(403, "Only an administrator can manage users")
    return user


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AppUser)
                     .where(AppUser.role == "ADMIN", AppUser.active.is_(True)))


@r.get("/users")
def list_users(_: AppUser = Depends(_admin), db: Session = Depends(get_db)):
    return [public(u) for u in db.scalars(select(AppUser).order_by(AppUser.username))]


@r.post("/users")
def create_user(body: NewUser, _: AppUser = Depends(_admin), db: Session = Depends(get_db)):
    if db.scalar(select(AppUser).where(AppUser.username == body.username)):
        raise HTTPException(409, "This username already exists")
    u = AppUser(username=body.username, password_hash=hash_password(body.password), role=body.role, active=True)
    db.add(u)
    db.commit()
    return public(u)


@r.put("/users/{uid}")
def update_user(uid: int, body: UserUpdate, me_: AppUser = Depends(_admin), db: Session = Depends(get_db)):
    u = db.get(AppUser, uid)
    if u is None:
        raise HTTPException(404, "User not found")
    losing_admin = u.role == "ADMIN" and u.active and (
        (body.role is not None and body.role != "ADMIN") or body.active is False)
    if losing_admin and _active_admins(db) <= 1:
        raise HTTPException(400, "At least one active administrator must remain")
    if u.id == me_.id and body.active is False:
        raise HTTPException(400, "You cannot deactivate yourself")
    if body.role is not None:
        u.role = body.role
    if body.active is not None:
        u.active = body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    db.commit()
    return public(u)


@r.delete("/users/{uid}")
def delete_user(uid: int, me_: AppUser = Depends(_admin), db: Session = Depends(get_db)):
    u = db.get(AppUser, uid)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == me_.id:
        raise HTTPException(400, "You cannot delete yourself")
    if u.role == "ADMIN" and u.active and _active_admins(db) <= 1:
        raise HTTPException(400, "At least one active administrator must remain")
    db.delete(u)
    db.commit()
    return {"ok": True}
