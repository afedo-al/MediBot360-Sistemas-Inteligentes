"""Capa de persistencia SQLite (gratuita y local) y datos semilla ficticios."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .security import hash_password

BASE_DIR = Path(__file__).resolve().parent.parent


def db_path() -> str:
    return os.environ.get("MEDIBOT_DB", str(BASE_DIR / "medibot.db"))


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','recepcion')));
CREATE TABLE IF NOT EXISTS specialties(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, price REAL NOT NULL,
  description TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS professionals(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL,
  specialty_id INTEGER NOT NULL REFERENCES specialties(id), active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS schedules(
  id INTEGER PRIMARY KEY, professional_id INTEGER NOT NULL REFERENCES professionals(id),
  weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
  start TEXT NOT NULL, end TEXT NOT NULL, slot_minutes INTEGER NOT NULL DEFAULT 30);
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY, alias TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  stage TEXT NOT NULL DEFAULT 'prospecto' CHECK(stage IN ('prospecto','contactado','cliente','inactivo')),
  source TEXT NOT NULL DEFAULT 'web', notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS interactions(
  id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  professional_id INTEGER NOT NULL REFERENCES professionals(id),
  visit_date TEXT NOT NULL, visit_time TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'confirmada' CHECK(status IN ('confirmada','cancelada','completada')),
  channel TEXT NOT NULL DEFAULT 'web', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE UNIQUE INDEX IF NOT EXISTS ux_slot_active ON appointments(professional_id, visit_date, visit_time)
  WHERE status IN ('confirmada','completada');
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY, appointment_id INTEGER NOT NULL REFERENCES appointments(id),
  amount REAL NOT NULL, method TEXT NOT NULL CHECK(method IN ('efectivo','tarjeta','transferencia')),
  invoice_folio TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS inventory(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, stock INTEGER NOT NULL DEFAULT 0,
  min_stock INTEGER NOT NULL DEFAULT 0, unit_cost REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS inventory_movements(
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES inventory(id),
  delta INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS chat_logs(
  id INTEGER PRIMARY KEY, intent TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL, action TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS contact_requests(
  id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
  alias TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL DEFAULT 'otro',
  status TEXT NOT NULL DEFAULT 'pendiente' CHECK(status IN ('pendiente','atendida','descartada')),
  handled_by TEXT NOT NULL DEFAULT '', handled_at TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS chat_events(
  id INTEGER PRIMARY KEY, session TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE INDEX IF NOT EXISTS ix_chat_events ON chat_events(event, session);
"""

# Columnas agregadas en versiones posteriores (migración ligera para bases existentes).
MIGRATIONS = [("appointments", "pin_hash", "TEXT NOT NULL DEFAULT ''")]

SPECIALTIES = [
    ("Medicina general", 450, "Valoración inicial y orientación médica general."),
    ("Cardiología", 850, "Consulta de seguimiento cardiovascular."),
    ("Dermatología", 650, "Cuidado de la piel, cabello y uñas."),
    ("Pediatría", 550, "Atención para niñas, niños y adolescentes."),
    ("Nutrición", 480, "Planes alimenticios personalizados."),
    ("Psicología", 600, "Sesiones de orientación psicológica."),
]
# (nombre, especialidad, días laborales, inicio, fin)
PROFESSIONALS = [
    ("Dra. Elena Rojas", "Medicina general", range(0, 6), "09:00", "17:00"),
    ("Dr. Daniel Vega", "Cardiología", range(0, 6), "09:00", "17:00"),
    ("Dra. Mariela Solís", "Dermatología", range(0, 6), "09:00", "17:00"),
    ("Dr. Emilio Lara", "Pediatría", range(0, 6), "09:00", "17:00"),
    ("L. N. Sofía Mora", "Nutrición", range(0, 6), "09:00", "17:00"),
    ("Psic. Andrea Chan", "Psicología", range(0, 6), "09:00", "17:00"),
    ("Dr. Andrés Pech", "Medicina general", range(0, 5), "11:00", "16:00"),
    ("Dra. Laura Canché", "Cardiología", (1, 3, 5), "09:00", "13:00"),
]
INVENTORY = [("Guantes de nitrilo (caja)", 20, 5, 120), ("Cubrebocas (caja)", 15, 5, 80),
             ("Gel antibacterial (litro)", 8, 3, 95), ("Papel para camilla (rollo)", 6, 4, 60),
             ("Abatelenguas (paquete)", 12, 4, 35)]


def init_db() -> None:
    admin_pw = os.environ.get("MEDIBOT_ADMIN_PASSWORD", "Admin#2026demo")
    recep_pw = os.environ.get("MEDIBOT_RECEPCION_PASSWORD", "Recepcion#2026demo")
    with connect() as db:
        db.executescript(SCHEMA)
        for table, col, ddl in MIGRATIONS:
            if col not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                       ("admin", hash_password(admin_pw), "admin"))
            db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                       ("recepcion", hash_password(recep_pw), "recepcion"))
        if db.execute("SELECT COUNT(*) FROM specialties").fetchone()[0] == 0:
            for name, price, desc in SPECIALTIES:
                db.execute("INSERT INTO specialties(name,price,description) VALUES(?,?,?)", (name, price, desc))
            for pname, sname, days, start, end in PROFESSIONALS:
                sid = db.execute("SELECT id FROM specialties WHERE name=?", (sname,)).fetchone()[0]
                pid = db.execute("INSERT INTO professionals(name,specialty_id) VALUES(?,?)", (pname, sid)).lastrowid
                for wd in days:  # sábado: media jornada
                    db.execute("INSERT INTO schedules(professional_id,weekday,start,end,slot_minutes) VALUES(?,?,?,?,?)",
                               (pid, wd, start, min(end, "13:00") if wd == 5 else end, 60))
        if db.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0:
            for n, s, m, c in INVENTORY:
                db.execute("INSERT INTO inventory(name,stock,min_stock,unit_cost) VALUES(?,?,?,?)", (n, s, m, c))
