# Warehouse Management System — React · Python · MySQL

The three-tier version of the single-file HTML warehouse app.

```
 React (Vite)  ──HTTP/JSON──▶  Python middleware (FastAPI + SQLAlchemy)  ──▶  MySQL 8
 frontend/                     backend/                                       database/schema.sql
 screens only                  all business rules live here                   single source of truth
```

Every rule from the HTML app that is ported runs **server-side**: strategies, capacity, task creation, cross-docking, GSTIN validation. The React app only displays data and calls the API, so other systems can use the same API and get identical behaviour.

---

## 1. Quick start with Docker (recommended)

Requires Docker Desktop (or Docker Engine + Compose).

```bash
docker compose up --build
```

| What | URL |
|---|---|
| Application | http://localhost:8080 |
| API + interactive docs | http://localhost:8000/docs |
| MySQL | localhost:3306 · db `wms` · user `wms` / `wms_pass` |

Then open the app, keep the **ADMIN** role, and press **Load demo**. That loads 3 warehouses: WH01 Bengaluru DC, WH02 Chennai DC and XD01 Hosur cross-dock hub.

Change the passwords before using it for real: `MYSQL_PASSWORD=... MYSQL_ROOT_PASSWORD=... docker compose up --build`.

## 2. Manual setup (development)

**MySQL 8**

```sql
CREATE DATABASE wms CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'wms'@'localhost' IDENTIFIED BY 'wms_pass';
GRANT ALL ON wms.* TO 'wms'@'localhost';
```

Tables are created automatically by the backend. To create them yourself, run `mysql -u root < database/schema.sql`.

**Python middleware** (Python 3.11+)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # adjust DATABASE_URL if needed
python -m app.seed                                     # optional: demo data (python -m app.seed --reset to start over)
uvicorn app.main:app --reload --port 8000
```

**React front end** (Node 18+)

```bash
cd frontend
npm install
npm run dev                                            # http://localhost:5173 — proxies /api to :8000
```

To run a single process instead, `npm run build` and start uvicorn. FastAPI then also serves `frontend/dist`, so everything is on http://localhost:8000.

## 3. Moving your data from the HTML app

1. In the old HTML app, press **Export** in the header. This saves `wms-data-YYYY-MM-DD.json`.
2. In the new app, go to **Enterprise → Migration**, choose the file and press **Import**. Tick *Replace all existing data* if the database is not empty.
   From the command line instead: `python -m app.import_legacy wms-data.json [--reset]`.

**What is imported:**
- enterprise structure (company codes, plants, storage locations);
- warehouses with address and GSTIN;
- storage types, sections, bin types, activity areas, queues, resource types, resources, work centers, doors, racks and bins;
- materials and BOMs;
- stock, with batch, serial, expiry and FIFO order;
- open ASNs and open sales orders.

Number ranges continue after the imported numbers.

**What is not imported:** history (old documents, waves, audit trail). It stays in the export file.

Warehouses each had their own material list in the HTML app. Here there is **one global material master**, merged by material code.

## 4. Tests

```bash
cd backend
pip install -r requirements-dev.txt
TEST_DATABASE_URL="mysql+pymysql://wms:wms_pass@localhost:3306/wms_test?charset=utf8mb4" pytest -q
```

The tests **drop and recreate** every table in the test database, so use an empty database (`wms_test`), never production. 13 end-to-end tests cover:
- GSTIN, PIN and state validation, and permissions;
- putaway executed by resources;
- wave release with BOM explosion, shortages and FEFO batch order;
- reach-level rules (a walking picker never gets level 2–3 bins);
- opportunistic cross-docking;
- rack preview, generation and its conflicts;
- the designer's draw, assign and delete;
- planned cross-docking;
- a stock transfer through the hub, both via the transfer screen and via normal wave and receive;
- creating a warehouse by copying another's structure;
- the GST exports;
- materials and BOMs;
- migration from the HTML app.

## 5. Project layout

```
backend/app/
  models.py          ORM models = the MySQL schema (python -m app.gen_schema > ../database/schema.sql)
  schemas.py         request validation (GSTIN / PAN / PIN rules live here)
  core.py            roles, errors, number ranges, audit
  services/
    engine.py        per-warehouse engine: capacity, putaway & pick strategies, BOM explosion,
                     documents, warehouse tasks (WT), warehouse orders (WO), resources
    racks.py         rack start → end bin generation, designer draw / assign / delete
    crossdock.py     planned & transport cross-docking
    transfers.py     stock transfers between warehouses (via hub)
    gst.py           GSTIN check-character validation
    exports.py       GST / address master data for other systems
  routers/           REST endpoints (see /docs)
  seed.py            demo data · import_legacy.py  migration from the HTML app
frontend/src/
  api.js ctx.jsx ui.jsx         API client, app state, shared components
  pages/                        one file per screen
database/schema.sql             generated DDL (38 tables, InnoDB, utf8mb4)
```

## 6. API at a glance

| Area | Endpoints (prefix `/api`) |
|---|---|
| Enterprise | `companies`, `plants`, `storage-locations`, `warehouses` (CRUD) · `gst/validate` · `stock-overview` |
| Integration | `exports/gst-master.json` · `exports/gst-master.csv` · `exports/transfers.json` |
| Organisation | `warehouses/{wh}/storage-types`, `sections`, `bin-types`, `activity-areas`, `queues`, `resource-types`, `resources`, `work-centers`, `doors` · `config` |
| Layout | `warehouses/{wh}/bins` · `designer/draw`, `designer/assign`, `designer/delete` · `racks`, `racks/preview`, `racks/{id}/generate`, `racks/{id}/delete-bins` |
| Materials | `materials`, `boms/{parent}` · `warehouses/{wh}/stock` |
| Execution | `asns`, `asns/{id}/receive` · `orders`, `waves` · `documents` · `tasks`, `tasks/confirm` · `warehouse-orders/{id}/assign`, `unassign`, `confirm` · `resources/{id}/logon`, `logoff`, `next` · `resources/auto-assign` · `resource-monitor` · `audit` |
| Cross-docking | `warehouses/{wh}/crossdock-orders` (+ `/receive`, `/confirm-moves`, `/goods-issue`) · `transfers` (+ `/release`, `/pick-and-ship`, `/hub-receive`, `/hub-confirm`, `/hub-dispatch`, `/receive`) |
| Admin | `admin/load-demo` · `admin/import-legacy` |

Business-rule violations return **400** with a readable `detail`. Invalid input returns **422**, and duplicate codes return **409**.

## 7. Before production

- **Login.** Users log in with a username and password; the role comes from the user (Users tab). The first visit creates the administrator. Set a random `AUTH_SECRET`.
- **Admin endpoints.** `admin/load-demo` and `admin/import-legacy?replace=true` wipe the database. Set `ALLOW_RESET=false` in production.
- **Empty the data.** `python -m app.clear_data --yes` deletes all warehouse data and keeps the users.
- **Secrets and backups.** Change the default MySQL passwords, restrict `CORS_ORIGINS` and set up MySQL backups.
- **Schema changes.** For changes after go-live, add Alembic migrations (`database/schema.sql` is generated from `models.py`).

## 8. Porting status

**Done** (server-side logic, API and React screens):
- multi-warehouse enterprise structure, with address and GSTIN captured for other systems (no billing);
- warehouse organisation units;
- racks generated from a start and end point, and the graphical layout designer;
- global materials and BOMs, and stock;
- putaway and pick strategies, and 2-step putaway and picking;
- ASNs, orders and waves;
- warehouse tasks and orders, queues and the resource monitor;
- planned, transport and opportunistic cross-docking, and stock transfers;
- the audit trail and migration from the HTML app.

**Still in the HTML app only.** The tables are not yet in the schema; each module needs its tables, a service, an API and a screen:
- slotting / ABC analysis and rearrangement;
- packaging specifications and handling units (SSCC);
- zero and low stock checks, and the difference analyzer;
- cycle counting / physical inventory;
- replenishment;
- kitting (VAS);
- yard management;
- the EWM alert monitor;
- manual bin-to-bin moves.
