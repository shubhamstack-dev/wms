"""Create all tables (idempotent):  python -m app.init_db"""
from . import models as m
from .auth import create_tables
from .db import engine

if __name__ == "__main__":
    m.Base.metadata.create_all(engine)
    create_tables()
    print("Tables created / verified:", len(m.Base.metadata.tables) + 1)
