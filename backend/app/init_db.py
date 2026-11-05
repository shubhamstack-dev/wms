"""Create all tables (idempotent):  python -m app.init_db"""
from . import models as m
from .db import engine

if __name__ == "__main__":
    m.Base.metadata.create_all(engine)
    print("Tables created / verified:", len(m.Base.metadata.tables))
