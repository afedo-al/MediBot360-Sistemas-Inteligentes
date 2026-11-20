"""
MediBot 360 - Auditoría final de entrega.

Solo consulta archivos y SQLite.
NO modifica, reinicia ni elimina información.
"""

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
custom_path = os.getenv("MEDIBOT_DB_PATH")
DB_PATH = (
    Path(custom_path).expanduser().resolve()
    if custom_path
    else ROOT / "database" / "medibot.db"
)
results = []


def check(label, success):
    success = bool(success)
    results.append((label, success))
    status = "OK" if success else "ERROR"
    print(f"[{status}] {label}")


def count(db, sql):
    return db.execute(sql).fetchone()[0]


print()
print("=" * 54)
print("     MEDIBOT 360 - AUDITORIA FINAL")
print("=" * 54)
print()

required_files = [
    "main.py",
    "create_admin.py",
    "app/database.py",
    "app/models.py",
    "app/security.py",
    "templates/index.html",
    "templates/reservar.html",
    "templates/admin.html",
    "templates/admin_appointments.html",
    "templates/admin_catalog.html",
    "templates/admin_schedules.html",
    "templates/admin_operations.html",
    "static/js/chatbot.js",
    "static/js/dashboard.js",
    "static/js/erp.js",
    "static/js/catalog.js",
    "static/js/erp_schedules.js",
    "static/js/erp_operations.js",
    "static/vendor/chart.umd.min.js",
    "static/css/chatbot.css",
    "static/css/admin.css",
    "tests/test_chatbot.py",
    "tests/test_security.py",
    "requirements.txt",
    "README.md",
    ".env.example"
]

print("1. ARCHIVOS")
for relative in required_files:
    check(relative, (ROOT / relative).is_file())

print()
print("2. BASE DE DATOS")
check("Base SQLite localizada", DB_PATH.is_file())

if DB_PATH.is_file():
    try:
        database_uri = DB_PATH.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as db:
            db.execute("PRAGMA query_only = ON")
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            check("Integridad general de SQLite", integrity == "ok")

            foreign_errors = db.execute("PRAGMA foreign_key_check").fetchone()
            check("Relaciones entre tablas", foreign_errors is None)

            tables = {
                row[0]
                for row in db.execute("""
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                """)
            }
            required_tables = {
                "users", "customers", "specialties", "professionals",
                "schedules", "appointments", "interactions", "payments",
                "resources", "schedule_day_settings", "resource_movements",
                "security_attempts"
            }
            check(
                "Tablas de todos los módulos",
                required_tables <= tables
            )

            if {"appointments", "payments"} <= tables:
                appointment_columns = {
                    row[1]
                    for row in db.execute("PRAGMA table_info(appointments)")
                }
                payment_columns = {
                    row[1]
                    for row in db.execute("PRAGMA table_info(payments)")
                }
                check(
                    "Precio acordado en reservaciones",
                    "agreed_price" in appointment_columns
                )
                check(
                    "Registro de devoluciones",
                    "refunded_at" in payment_columns
                )

            if {"appointments", "schedules"} <= tables:
                mismatches = count(db, """
                    SELECT COUNT(*)
                    FROM appointments a
                    JOIN schedules s ON s.id = a.schedule_id
                    WHERE a.status = 'confirmed'
                      AND (
                          s.status <> 'reserved'
                          OR a.professional_id <> s.professional_id
                      )
                """)
                check("Citas confirmadas coherentes", mismatches == 0)

                orphan_slots = count(db, """
                    SELECT COUNT(*)
                    FROM schedules s
                    WHERE s.status = 'reserved'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM appointments a
                          WHERE a.schedule_id = s.id
                            AND a.status = 'confirmed'
                      )
                """)
                check("Horarios reservados con cita", orphan_slots == 0)

                duplicates = count(db, """
                    SELECT COUNT(*)
                    FROM (
                        SELECT schedule_id
                        FROM appointments
                        WHERE status = 'confirmed'
                        GROUP BY schedule_id
                        HAVING COUNT(*) > 1
                    )
                """)
                check("Sin doble reservación", duplicates == 0)

            if "resources" in tables:
                negatives = count(db, """
                    SELECT COUNT(*)
                    FROM resources
                    WHERE quantity < 0
                """)
                check("Sin existencias negativas", negatives == 0)

            if "payments" in tables:
                multiple_payments = count(db, """
                    SELECT COUNT(*)
                    FROM (
                        SELECT appointment_id
                        FROM payments
                        GROUP BY appointment_id
                        HAVING COUNT(*) > 1
                    )
                """)
                check(
                    "Sin pagos duplicados por cita",
                    multiple_payments == 0
                )

                negative_payments = count(db, """
                    SELECT COUNT(*)
                    FROM payments
                    WHERE amount < 0
                """)
                check("Sin pagos negativos", negative_payments == 0)

            if {
                "schedule_day_settings",
                "appointments",
                "schedules"
            } <= tables:
                closed_conflicts = count(db, """
                    SELECT COUNT(*)
                    FROM appointments a
                    JOIN schedules s ON s.id = a.schedule_id
                    JOIN schedule_day_settings d
                      ON d.professional_id = s.professional_id
                     AND d.appointment_date = s.appointment_date
                    WHERE a.status = 'confirmed'
                      AND d.is_closed = 1
                """)
                check(
                    "Sin citas activas en días cerrados",
                    closed_conflicts == 0
                )
    except sqlite3.Error as error:
        check(f"Lectura de SQLite: {error}", False)

total = len(results)
failed = sum(not success for _, success in results)
passed = total - failed

print()
print("=" * 54)
print(f"RESULTADO: {passed}/{total} comprobaciones")
print("=" * 54)

if failed:
    print("Hay pendientes que deben revisarse antes de la entrega.")
    sys.exit(1)

print("La estructura y las verificaciones de integridad están correctas.")
