"""WMS middleware — FastAPI application."""
import os
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from .config import CORS_ORIGINS
from .core import BizError, get_role, require
from .routers import enterprise, org, layout, materials, flows, xdock

app = FastAPI(title="Warehouse Management System API", version="2.0.0",
              description="React front end · Python (FastAPI) middleware · MySQL database")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(BizError)
async def biz_error(_: Request, exc: BizError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    msg = str(exc.orig)
    if "Duplicate" in msg or "UNIQUE" in msg:
        return JSONResponse(status_code=409, content={"detail": "This code already exists"})
    return JSONResponse(status_code=409, content={"detail": "Change rejected by the database (still referenced?)"})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/admin/load-demo")
def load_demo(role: str = Depends(get_role)):
    """ADMIN only: drops all WMS tables and loads the 3-warehouse demo."""
    require(role, "reset")
    from .seed import reset_and_seed
    return reset_and_seed()


@app.post("/api/admin/import-legacy")
def import_legacy(payload: dict, replace: bool = False, role: str = Depends(get_role)):
    """ADMIN only: import the JSON exported by the single-file HTML app. replace=true wipes the database first."""
    require(role, "reset")
    from . import models as m
    from .db import engine, SessionLocal
    from .import_legacy import import_data
    if replace:
        m.Base.metadata.drop_all(engine)
        m.Base.metadata.create_all(engine)
    with SessionLocal() as db:
        try:
            return import_data(db, payload)
        except SystemExit as e:
            raise BizError(str(e))


for mod in (enterprise, org, layout, materials, flows, xdock):
    app.include_router(mod.r, prefix="/api")

# Optional: serve the built React app from the same process (single-container deploy)
_dist = os.getenv("FRONTEND_DIST", os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(os.path.join(_dist, "index.html"))
