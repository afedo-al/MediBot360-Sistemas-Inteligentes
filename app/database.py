
import os
import sqlite3

from pathlib import Path
from contextlib import contextmanager

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"

DATABASE_DIR.mkdir(exist_ok=True)

custom_database = os.getenv("MEDIBOT_DB_PATH")

if custom_database:
    DATABASE_PATH = Path(custom_database).expanduser().resolve()
else:
    DATABASE_PATH = DATABASE_DIR / "medibot.db"

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
