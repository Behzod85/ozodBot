#!/usr/bin/env python3
"""Create the SQLite database file `ozodbot.db` and initialize schema.

Run from the repository root:

    python3 scripts/create_db.py

This script calls `models.init_db()` which will create tables and apply
non-destructive migrations where possible.
"""
import os
import sys

# Ensure repository root is on sys.path so `from models import ...` works
SCRIPT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from models import init_db, DB_URL


def main():
    print(f"Initializing database using DB_URL={DB_URL}")
    try:
        init_db()
    except Exception as e:
        print("Failed to initialize database:", e, file=sys.stderr)
        return 2

    if DB_URL.startswith("sqlite:///"):
        db_file = DB_URL[len("sqlite:///"):]
        exists = os.path.exists(db_file)
        print(f"Database file: {db_file} (exists={exists})")
    else:
        print("Database initialized (non-sqlite DB_URL).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
