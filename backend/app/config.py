import os
from pathlib import Path


def _load_dotenv():
    """Minimal .env loader (backend/.env) — real environment variables always win."""
    f = Path(__file__).resolve().parent.parent / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://wms:wms_pass@localhost:3306/wms?charset=utf8mb4")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# Login tokens are signed with this. Set a long random value in production.
AUTH_SECRET = os.getenv("AUTH_SECRET", "dev-only-secret-change-me")
AUTH_HOURS = float(os.getenv("AUTH_HOURS", "12"))
# false = "Load demo" and "replace all data" import are switched off (production)
ALLOW_RESET = os.getenv("ALLOW_RESET", "true").strip().lower() in ("1", "true", "yes")
