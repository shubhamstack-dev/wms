"""Regenerate database/schema.sql from the ORM models:  python -m app.gen_schema > ../database/schema.sql"""
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable, CreateIndex
from . import models as m

HEADER = """-- ============================================================================
-- Warehouse Management System — MySQL 8 schema
-- Generated from backend/app/models.py (python -m app.gen_schema). Do not edit by hand.
-- ============================================================================
CREATE DATABASE IF NOT EXISTS wms CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE wms;
SET FOREIGN_KEY_CHECKS = 0;
"""

if __name__ == "__main__":
    d = mysql.dialect()
    print(HEADER)
    for t in m.Base.metadata.sorted_tables:
        print(f"DROP TABLE IF EXISTS `{t.name}`;")
    print()
    for t in m.Base.metadata.sorted_tables:
        ddl = str(CreateTable(t).compile(dialect=d)).strip()
        print(ddl + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n")
        for ix in sorted(t.indexes, key=lambda i: i.name):
            print(str(CreateIndex(ix).compile(dialect=d)).strip() + ";")
        print()
    print("SET FOREIGN_KEY_CHECKS = 1;")
