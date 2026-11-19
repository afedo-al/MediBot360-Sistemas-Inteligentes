
from datetime import date, timedelta

from app.database import get_db


def initialize_database():

    with get_db() as db:

        db.executescript("""

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS specialties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS professionals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            specialty_id INTEGER NOT NULL,
            email TEXT,
            active INTEGER DEFAULT 1,
            FOREIGN KEY (specialty_id)
                REFERENCES specialties(id)
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professional_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            FOREIGN KEY (professional_id)
                REFERENCES professionals(id),
            UNIQUE(professional_id, appointment_date, start_time)
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL,
            customer_id INTEGER NOT NULL,
            professional_id INTEGER NOT NULL,
            schedule_id INTEGER NOT NULL,
            status TEXT DEFAULT 'confirmed',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id)
                REFERENCES customers(id),
            FOREIGN KEY (professional_id)
                REFERENCES professionals(id),
            FOREIGN KEY (schedule_id)
                REFERENCES schedules(id)
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            message TEXT NOT NULL,
            response TEXT,
            channel TEXT DEFAULT 'chatbot',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id)
                REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_date DATETIME,
            FOREIGN KEY (appointment_id)
                REFERENCES appointments(id)
        );

        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            quantity INTEGER DEFAULT 0,
            status TEXT DEFAULT 'available'
        );

        """)

def seed_specialties():

    specialties = [
        ("Medicina general", "Consulta médica general", 450),
        ("Cardiología", "Atención especializada cardiovascular", 850),
        ("Dermatología", "Atención especializada de la piel", 650),
        ("Pediatría", "Atención médica infantil", 550),
        ("Nutrición", "Orientación nutricional", 480),
        ("Psicología", "Orientación psicológica", 600)
    ]

    with get_db() as db:

        for name, description, price in specialties:

            db.execute("""
                INSERT OR IGNORE INTO specialties
                (name, description, price)
                VALUES (?, ?, ?)
            """, (name, description, price))


def seed_professionals():
    professionals = [
        ("Dra. Elena Rojas", "Medicina general"),
        ("Dr. Daniel Vega", "Cardiología"),
        ("Dra. Mariela Solís", "Dermatología"),
        ("Dr. Emilio Lara", "Pediatría"),
        ("L. N. Sofía Mora", "Nutrición"),
        ("Psic. Andrea Chan", "Psicología")
    ]

    with get_db() as db:
        for full_name, specialty_name in professionals:
            specialty = db.execute("""
                SELECT id
                FROM specialties
                WHERE name = ?
            """, (specialty_name,)).fetchone()

            if specialty is None:
                continue

            existing = db.execute("""
                SELECT id
                FROM professionals
                WHERE full_name = ?
                AND specialty_id = ?
            """, (full_name, specialty["id"])).fetchone()

            if existing is None:
                db.execute("""
                    INSERT INTO professionals
                    (full_name, specialty_id, active)
                    VALUES (?, ?, 1)
                """, (full_name, specialty["id"]))


def seed_schedules():
    appointment_hours = [
        ("09:00", "10:00"),
        ("10:00", "11:00"),
        ("11:00", "12:00"),
        ("12:00", "13:00"),
        ("16:00", "17:00"),
        ("17:00", "18:00")
    ]

    with get_db() as db:
        professionals = db.execute("""
            SELECT id
            FROM professionals
            WHERE active = 1
        """).fetchall()

        for professional in professionals:
            for offset in range(1, 15):
                appointment_day = date.today() + timedelta(days=offset)

                # Lunes a sábado
                if appointment_day.weekday() == 6:
                    continue

                for start_time, end_time in appointment_hours:
                    db.execute("""
                        INSERT OR IGNORE INTO schedules
                        (
                            professional_id,
                            appointment_date,
                            start_time,
                            end_time,
                            status
                        )
                        VALUES (?, ?, ?, ?, 'available')
                    """, (
                        professional["id"],
                        appointment_day.isoformat(),
                        start_time,
                        end_time
                    ))
