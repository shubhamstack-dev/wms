"""Delete ALL warehouse data (demo or real) and start with empty tables.
User accounts are kept.   python -m app.clear_data --yes"""
import sys
from . import models as m
from .db import engine

if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit("This deletes every warehouse, material, stock and document. Run again with --yes")
    m.Base.metadata.drop_all(engine)
    m.Base.metadata.create_all(engine)
    print("All WMS data deleted. Tables are empty. Users were kept.")
