
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Literal
from starlette.middleware.sessions import SessionMiddleware
from urllib.parse import urlsplit

from contextlib import asynccontextmanager

from app.database import get_db
from app.models import (
    initialize_database,
    seed_specialties,
    seed_professionals,
    seed_schedules
)
from app.security import verify_password


load_dotenv()

SESSION_SECRET = os.getenv("MEDIBOT_SESSION_SECRET")

if not SESSION_SECRET:
    raise RuntimeError(
        "No se encontró MEDIBOT_SESSION_SECRET en el archivo .env"
    )


class AppointmentRequest(BaseModel):
    schedule_id: int = Field(gt=0)
    full_name: str = Field(
        min_length=3,
        max_length=150
    )
    email: str | None = Field(
        default=None,
        max_length=150
    )
    phone: str | None = Field(
        default=None,
        max_length=20
    )
    source: Literal["web", "chatbot"] = "web"


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=100
    )
    password: str = Field(
        min_length=1,
        max_length=200
    )


class SpecialtyRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    price: float = Field(gt=0)
    active: bool = True


class ProfessionalRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=150)
    specialty_id: int = Field(gt=0)
    email: str | None = Field(default=None, max_length=150)
    active: bool = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    seed_specialties()
    seed_professionals()
    seed_schedules()
    yield
    
app = FastAPI(
    title="MediBot 360",
    description="Plataforma de coordinación de servicios médicos",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="medibot_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=(
        os.getenv("MEDIBOT_HTTPS", "0") == "1"
    )
)

# Directorio principal del proyecto
BASE_DIR = Path(__file__).resolve().parent

# Archivos estáticos
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

# Plantillas HTML
templates = Jinja2Templates(
    directory=BASE_DIR / "templates"
)


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "MediBot 360"}
    )


@app.get("/reservar")
async def reservation_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="reservar.html",
        context={
            "title": "Reservar una cita | MediBot 360"
        }
    )


@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "application": "MediBot 360",
        "version": "1.0.0"
    }


@app.get("/api/specialties")
async def get_specialties():
    with get_db() as db:
        specialties = db.execute("""
            SELECT id, name, description, price
            FROM specialties
            WHERE active = 1
            ORDER BY id
        """).fetchall()

    return {
        "success": True,
        "total": len(specialties),
        "data": [dict(item) for item in specialties]
    }


@app.get("/api/professionals/{specialty_id}")
async def get_professionals(specialty_id: int):
    with get_db() as db:
        professionals = db.execute("""
            SELECT
                professionals.id,
                professionals.full_name,
                professionals.email,
                specialties.name AS specialty
            FROM professionals
            INNER JOIN specialties
                ON professionals.specialty_id = specialties.id
            WHERE professionals.specialty_id = ?
            AND professionals.active = 1
            AND specialties.active = 1
            ORDER BY professionals.full_name
        """, (specialty_id,)).fetchall()

    return {
        "success": True,
        "total": len(professionals),
        "data": [dict(item) for item in professionals]
    }


@app.get("/api/schedules")
async def get_available_schedules(
    professional_id: int,
    appointment_date: str
):
    try:
        date.fromisoformat(appointment_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener el formato YYYY-MM-DD."
        )

    with get_db() as db:
        schedules = db.execute("""
            SELECT
                id,
                professional_id,
                appointment_date,
                start_time,
                end_time
            FROM schedules
            WHERE professional_id = ?
            AND appointment_date = ?
            AND status = 'available'
            AND NOT EXISTS (
                SELECT 1
                FROM schedule_day_settings ds
                WHERE ds.professional_id = schedules.professional_id
                  AND ds.appointment_date = schedules.appointment_date
                  AND ds.is_closed = 1
            )
            AND EXISTS (
                SELECT 1
                FROM professionals p
                INNER JOIN specialties sp
                    ON sp.id = p.specialty_id
                WHERE p.id = schedules.professional_id
                  AND p.active = 1
                  AND sp.active = 1
            )
            ORDER BY start_time
        """, (professional_id, appointment_date)).fetchall()

    return {
        "success": True,
        "total": len(schedules),
        "data": [dict(item) for item in schedules]
    }


@app.post("/api/appointments")
async def create_appointment(
    appointment: AppointmentRequest,
    request: Request
):
    check_rate_limit(
        request, "new_booking", maximum=15
    )
    full_name = appointment.full_name.strip()
    email = appointment.email.strip().lower() if appointment.email else None
    phone = appointment.phone.strip() if appointment.phone else None

    if len(full_name) < 3:
        raise HTTPException(
            status_code=400,
            detail="Ingresa un nombre válido."
        )

    folio = f"MB-{secrets.token_hex(4).upper()}"

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        schedule = db.execute("""
            SELECT
                s.id,
                s.professional_id,
                s.appointment_date,
                s.status,
                p.active AS professional_active,
                sp.active AS specialty_active,
                sp.price AS agreed_price
            FROM schedules s
            INNER JOIN professionals p
                ON p.id = s.professional_id
            INNER JOIN specialties sp
                ON sp.id = p.specialty_id
            WHERE s.id = ?
        """, (appointment.schedule_id,)).fetchone()

        if schedule is None:
            raise HTTPException(
                status_code=404,
                detail="El horario seleccionado no existe."
            )

        if (
            not schedule["professional_active"]
            or not schedule["specialty_active"]
        ):
            raise HTTPException(
                status_code=409,
                detail="El servicio o profesional no está disponible."
            )

        appointment_day = date.fromisoformat(
            schedule["appointment_date"]
        )

        if not (
            date.today() < appointment_day
            <= date.today() + timedelta(days=14)
        ):
            raise HTTPException(
                status_code=400,
                detail="La fecha está fuera del periodo de reservación."
            )

        if appointment_day.weekday() == 6:
            raise HTTPException(
                status_code=400,
                detail="No se permiten reservaciones los domingos."
            )

        if schedule["status"] != "available":
            raise HTTPException(
                status_code=409,
                detail="Este horario ya no está disponible."
            )

        if is_schedule_day_closed(
            db,
            schedule["professional_id"],
            schedule["appointment_date"]
        ):
            raise HTTPException(
                status_code=409,
                detail="Este día está cerrado para reservaciones."
            )

        updated = db.execute("""
            UPDATE schedules
            SET status = 'reserved'
            WHERE id = ?
            AND status = 'available'
        """, (appointment.schedule_id,))

        if updated.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="Este horario ya no está disponible."
            )

        customer = None
        if email:
            customer = db.execute("""
                SELECT id
                FROM customers
                WHERE email = ?
            """, (email,)).fetchone()

        if customer is None:
            db.execute("""
                INSERT INTO customers
                (full_name, email, phone)
                VALUES (?, ?, ?)
            """, (full_name, email, phone))

            customer = db.execute("""
                SELECT id
                FROM customers
                WHERE id = last_insert_rowid()
            """).fetchone()
        else:
            db.execute("""
                UPDATE customers
                SET full_name = ?,
                    phone = COALESCE(?, phone)
                WHERE id = ?
            """, (full_name, phone, customer["id"]))

        db.execute("""
            INSERT INTO appointments
            (
                folio,
                customer_id,
                professional_id,
                schedule_id,
                status,
                agreed_price
            )
            VALUES (?, ?, ?, ?, 'confirmed', ?)
        """, (
            folio,
            customer["id"],
            schedule["professional_id"],
            appointment.schedule_id,
            round(float(schedule["agreed_price"]), 2)
        ))

        appointment_row = db.execute("""
            SELECT id
            FROM appointments
            WHERE folio = ?
        """, (folio,)).fetchone()

        db.execute("""
            INSERT INTO interactions
            (customer_id, message, response, channel)
            VALUES (?, ?, ?, ?)
        """, (
            customer["id"],
            "Solicitud de reservación",
            f"Reservación creada con folio {folio}",
            appointment.source
        ))

    return {
        "success": True,
        "folio": folio,
        "appointment_id": appointment_row["id"],
        "message": "Reservación creada exitosamente."
    }


def get_current_admin(request: Request):
    user_id = request.session.get("user_id")

    if not user_id:
        return None

    with get_db() as db:
        user = db.execute("""
            SELECT id, username, role
            FROM users
            WHERE id = ?
        """, (user_id,)).fetchone()

    if user is None or user["role"] != "admin":
        request.session.clear()
        return None

    return dict(user)


def require_admin(request: Request):
    admin = get_current_admin(request)

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    return admin


def is_schedule_day_closed(db, professional_id: int, appointment_date: str):
    return db.execute("""
        SELECT 1
        FROM schedule_day_settings
        WHERE professional_id = ?
          AND appointment_date = ?
          AND is_closed = 1
    """, (professional_id, appointment_date)).fetchone() is not None


def has_pending_confirmed_appointments(
    db,
    column: str,
    record_id: int
):
    if column not in {"p.specialty_id", "a.professional_id"}:
        raise ValueError("Columna no permitida.")

    return db.execute(f"""
        SELECT 1
        FROM appointments a
        INNER JOIN schedules s
            ON s.id = a.schedule_id
        INNER JOIN professionals p
            ON p.id = a.professional_id
        WHERE a.status = 'confirmed'
        AND s.appointment_date >= ?
        AND {column} = ?
        LIMIT 1
    """, (date.today().isoformat(), record_id)).fetchone() is not None


# ==================================================
# ETAPA 10B - LIMITADOR DE INTENTOS
# ==================================================

def check_rate_limit(
    request: Request,
    action: str,
    maximum: int,
    window_seconds: int = 900
):
    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    fingerprint = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        f"{action}:{client_ip}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    now = int(time.time())
    cutoff = now - window_seconds

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            DELETE FROM security_attempts
            WHERE created_at < ?
        """, (now - 86400,))

        total = db.execute("""
            SELECT COUNT(*) AS attempts
            FROM security_attempts
            WHERE fingerprint = ?
              AND created_at > ?
        """, (fingerprint, cutoff)).fetchone()["attempts"]

        if total >= maximum:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Demasiados intentos. "
                    "Intenta nuevamente más tarde."
                ),
                headers={
                    "Retry-After": str(window_seconds)
                }
            )

        db.execute("""
            INSERT INTO security_attempts
                (fingerprint, created_at)
            VALUES (?, ?)
        """, (fingerprint, now))


@app.post("/api/auth/login")
async def login(data: LoginRequest, request: Request):
    check_rate_limit(
        request, "admin_login", maximum=10
    )
    username = data.username.strip().lower()

    with get_db() as db:
        user = db.execute("""
            SELECT id, username, password_hash, role
            FROM users
            WHERE username = ?
        """, (username,)).fetchone()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos."
        )

    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos."
        )

    if user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos administrativos."
        )

    request.session.clear()
    request.session["user_id"] = user["id"]

    return {
        "success": True,
        "message": "Inicio de sesión correcto.",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"]
        }
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()

    return {
        "success": True,
        "message": "Sesión cerrada correctamente."
    }


@app.get("/admin/login")
async def admin_login_page(request: Request):
    admin = get_current_admin(request)

    if admin:
        return RedirectResponse(
            url="/admin",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={
            "title": "Acceso administrativo | MediBot 360"
        }
    )


@app.get("/admin")
async def admin_dashboard(request: Request):
    admin = get_current_admin(request)

    if not admin:
        return RedirectResponse(
            url="/admin/login",
            status_code=303
        )

    with get_db() as db:
        total_customers = db.execute("""
            SELECT COUNT(*) AS total
            FROM customers
        """).fetchone()["total"]

        total_appointments = db.execute("""
            SELECT COUNT(*) AS total
            FROM appointments
        """).fetchone()["total"]

        confirmed_appointments = db.execute("""
            SELECT COUNT(*) AS total
            FROM appointments
            WHERE status = 'confirmed'
        """).fetchone()["total"]

        booked_schedules = db.execute("""
            SELECT COUNT(*) AS total
            FROM schedules
            WHERE status = 'reserved'
        """).fetchone()["total"]

        recent_appointments = db.execute("""
            SELECT
                a.folio,
                a.status,
                c.full_name AS customer_name,
                p.full_name AS professional_name,
                sp.name AS specialty_name,
                s.appointment_date,
                s.start_time
            FROM appointments a
            INNER JOIN customers c
                ON a.customer_id = c.id
            INNER JOIN professionals p
                ON a.professional_id = p.id
            INNER JOIN specialties sp
                ON p.specialty_id = sp.id
            INNER JOIN schedules s
                ON a.schedule_id = s.id
            ORDER BY a.created_at DESC
            LIMIT 6
        """).fetchall()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "title": "Panel administrativo | MediBot 360",
            "admin": admin,
            "stats": {
                "customers": total_customers,
                "appointments": total_appointments,
                "confirmed": confirmed_appointments,
                "booked": booked_schedules
            },
            "recent_appointments": [
                dict(item) for item in recent_appointments
            ]
        }
    )


# ============================================
# ERP - CATÁLOGO DE SERVICIOS Y PROFESIONALES
# ============================================

@app.get("/admin/catalogo")
async def catalog_page(request: Request):
    admin = get_current_admin(request)

    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_catalog.html",
        context={
            "title": "Catálogo | MediBot 360",
            "admin": admin
        }
    )


@app.get("/api/admin/specialties")
async def admin_get_specialties(request: Request):
    require_admin(request)

    with get_db() as db:
        specialties = db.execute("""
            SELECT
                s.id,
                s.name,
                s.description,
                s.price,
                s.active,
                COUNT(DISTINCT p.id) AS professionals_count
            FROM specialties s
            LEFT JOIN professionals p
                ON p.specialty_id = s.id
            GROUP BY s.id
            ORDER BY s.name
        """).fetchall()

    return {
        "success": True,
        "data": [dict(item) for item in specialties]
    }


@app.post("/api/admin/specialties")
async def admin_create_specialty(
    data: SpecialtyRequest,
    request: Request
):
    require_admin(request)
    name = data.name.strip()
    description = data.description.strip()

    if len(name) < 2:
        raise HTTPException(
            status_code=400,
            detail="El nombre de la especialidad es obligatorio."
        )

    try:
        with get_db() as db:
            cursor = db.execute("""
                INSERT INTO specialties (name, description, price, active)
                VALUES (?, ?, ?, ?)
            """, (name, description, data.price, int(data.active)))
            specialty = db.execute("""
                SELECT id, name, description, price, active
                FROM specialties
                WHERE id = ?
            """, (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una especialidad con ese nombre."
        )

    return {"success": True, "data": dict(specialty)}


@app.put("/api/admin/specialties/{specialty_id}")
async def admin_update_specialty(
    specialty_id: int,
    data: SpecialtyRequest,
    request: Request
):
    require_admin(request)
    name = data.name.strip()
    description = data.description.strip()

    if len(name) < 2:
        raise HTTPException(
            status_code=400,
            detail="El nombre de la especialidad es obligatorio."
        )

    try:
        with get_db() as db:
            current = db.execute("""
                SELECT id, active
                FROM specialties
                WHERE id = ?
            """, (specialty_id,)).fetchone()

            if current is None:
                raise HTTPException(
                    status_code=404,
                    detail="La especialidad no existe."
                )

            if current["active"] and not data.active:
                if has_pending_confirmed_appointments(
                    db, "p.specialty_id", specialty_id
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "No se puede desactivar la especialidad porque "
                            "tiene citas confirmadas pendientes."
                        )
                    )

            db.execute("""
                UPDATE specialties
                SET name = ?, description = ?, price = ?, active = ?
                WHERE id = ?
            """, (
                name,
                description,
                data.price,
                int(data.active),
                specialty_id
            ))
            specialty = db.execute("""
                SELECT id, name, description, price, active
                FROM specialties
                WHERE id = ?
            """, (specialty_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una especialidad con ese nombre."
        )

    if data.active:
        seed_schedules()

    return {"success": True, "data": dict(specialty)}


@app.get("/api/admin/professionals")
async def admin_get_professionals(request: Request):
    require_admin(request)

    with get_db() as db:
        professionals = db.execute("""
            SELECT
                p.id,
                p.full_name,
                p.email,
                p.active,
                p.specialty_id,
                s.name AS specialty_name,
                s.active AS specialty_active
            FROM professionals p
            INNER JOIN specialties s
                ON s.id = p.specialty_id
            ORDER BY p.full_name
        """).fetchall()

    return {
        "success": True,
        "data": [dict(item) for item in professionals]
    }


@app.post("/api/admin/professionals")
async def admin_create_professional(
    data: ProfessionalRequest,
    request: Request
):
    require_admin(request)
    full_name = data.full_name.strip()
    email = data.email.strip().lower() if data.email else None

    if len(full_name) < 3:
        raise HTTPException(
            status_code=400,
            detail="El nombre del profesional es obligatorio."
        )

    with get_db() as db:
        specialty = db.execute("""
            SELECT id
            FROM specialties
            WHERE id = ?
        """, (data.specialty_id,)).fetchone()

        if specialty is None:
            raise HTTPException(
                status_code=404,
                detail="La especialidad seleccionada no existe."
            )

        cursor = db.execute("""
            INSERT INTO professionals
            (full_name, specialty_id, email, active)
            VALUES (?, ?, ?, ?)
        """, (
            full_name,
            data.specialty_id,
            email,
            int(data.active)
        ))
        professional = db.execute("""
            SELECT
                p.id,
                p.full_name,
                p.email,
                p.active,
                p.specialty_id,
                s.name AS specialty_name
            FROM professionals p
            INNER JOIN specialties s ON s.id = p.specialty_id
            WHERE p.id = ?
        """, (cursor.lastrowid,)).fetchone()

    if data.active:
        seed_schedules()

    return {"success": True, "data": dict(professional)}


@app.put("/api/admin/professionals/{professional_id}")
async def admin_update_professional(
    professional_id: int,
    data: ProfessionalRequest,
    request: Request
):
    require_admin(request)
    full_name = data.full_name.strip()
    email = data.email.strip().lower() if data.email else None

    if len(full_name) < 3:
        raise HTTPException(
            status_code=400,
            detail="El nombre del profesional es obligatorio."
        )

    with get_db() as db:
        current = db.execute("""
            SELECT id, active, specialty_id
            FROM professionals
            WHERE id = ?
        """, (professional_id,)).fetchone()

        if current is None:
            raise HTTPException(
                status_code=404,
                detail="El profesional no existe."
            )

        specialty = db.execute("""
            SELECT id
            FROM specialties
            WHERE id = ?
        """, (data.specialty_id,)).fetchone()

        if specialty is None:
            raise HTTPException(
                status_code=404,
                detail="La especialidad seleccionada no existe."
            )

        if (
            current["specialty_id"] != data.specialty_id
            and has_pending_confirmed_appointments(
                db, "a.professional_id", professional_id
            )
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "No se puede cambiar la especialidad porque el "
                    "profesional tiene citas confirmadas pendientes."
                )
            )

        if current["active"] and not data.active:
            if has_pending_confirmed_appointments(
                db, "a.professional_id", professional_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "No se puede desactivar el profesional porque "
                        "tiene citas confirmadas pendientes."
                    )
                )

        db.execute("""
            UPDATE professionals
            SET full_name = ?, specialty_id = ?, email = ?, active = ?
            WHERE id = ?
        """, (
            full_name,
            data.specialty_id,
            email,
            int(data.active),
            professional_id
        ))
        professional = db.execute("""
            SELECT
                p.id,
                p.full_name,
                p.email,
                p.active,
                p.specialty_id,
                s.name AS specialty_name
            FROM professionals p
            INNER JOIN specialties s ON s.id = p.specialty_id
            WHERE p.id = ?
        """, (professional_id,)).fetchone()

    if data.active:
        seed_schedules()

    return {"success": True, "data": dict(professional)}


# ============================================
# CRM - GESTIÓN DE CLIENTES
# ============================================

@app.get("/admin/clientes")
async def crm_customers_page(request: Request):
    admin = get_current_admin(request)

    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_customers.html",
        context={
            "title": "Clientes | MediBot 360",
            "admin": admin
        }
    )


@app.get("/admin/clientes/{customer_id}")
async def crm_customer_profile(customer_id: int, request: Request):
    admin = get_current_admin(request)

    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    with get_db() as db:
        customer = db.execute("""
            SELECT *
            FROM customers
            WHERE id = ?
        """, (customer_id,)).fetchone()

        if not customer:
            return RedirectResponse(url="/admin/clientes", status_code=303)

        appointments = db.execute("""
            SELECT
                a.id,
                a.folio,
                a.status,
                s.appointment_date,
                s.start_time,
                s.end_time,
                p.full_name AS professional_name,
                sp.name AS specialty_name,
                sp.price
            FROM appointments a
            INNER JOIN schedules s ON a.schedule_id = s.id
            INNER JOIN professionals p ON a.professional_id = p.id
            INNER JOIN specialties sp ON p.specialty_id = sp.id
            WHERE a.customer_id = ?
            ORDER BY s.appointment_date DESC, s.start_time DESC
        """, (customer_id,)).fetchall()

        interactions = db.execute("""
            SELECT *
            FROM interactions
            WHERE customer_id = ?
            ORDER BY created_at DESC
        """, (customer_id,)).fetchall()

    return templates.TemplateResponse(
        request=request,
        name="admin_customer_profile.html",
        context={
            "title": "Cliente | MediBot 360",
            "admin": admin,
            "customer": dict(customer),
            "appointments": [dict(item) for item in appointments],
            "interactions": [dict(item) for item in interactions]
        }
    )


@app.get("/api/admin/customers")
async def crm_get_customers(
    request: Request,
    search: str = Query(default="", max_length=100)
):
    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    search = search.strip()

    with get_db() as db:
        customers = db.execute("""
            SELECT
                c.id,
                c.full_name,
                c.email,
                c.phone,
                c.status,
                c.created_at,
                COUNT(DISTINCT a.id) AS appointments_count,
                MAX(a.created_at) AS last_appointment
            FROM customers c
            LEFT JOIN appointments a ON a.customer_id = c.id
            WHERE c.full_name LIKE ?
               OR COALESCE(c.email, '') LIKE ?
               OR COALESCE(c.phone, '') LIKE ?
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()

    return {
        "success": True,
        "total": len(customers),
        "data": [dict(customer) for customer in customers]
    }


@app.get("/api/admin/customers/{customer_id}")
async def crm_get_customer(customer_id: int, request: Request):
    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    with get_db() as db:
        customer = db.execute("""
            SELECT *
            FROM customers
            WHERE id = ?
        """, (customer_id,)).fetchone()

    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    return {"success": True, "data": dict(customer)}


class CustomerUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(default="", max_length=150)
    phone: str = Field(default="", max_length=30)
    status: str = Field(default="active")


@app.put("/api/admin/customers/{customer_id}")
async def crm_update_customer(
    customer_id: int,
    data: CustomerUpdate,
    request: Request
):
    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    full_name = data.full_name.strip()
    email = data.email.strip().lower()
    phone = data.phone.strip()

    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="Ingresa un nombre válido.")
    if data.status not in {"active", "inactive"}:
        raise HTTPException(status_code=400, detail="Estado de cliente inválido.")
    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="El correo electrónico no es válido.")

    with get_db() as db:
        customer = db.execute(
            "SELECT id FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.")

        if email:
            duplicate = db.execute("""
                SELECT id
                FROM customers
                WHERE email = ? AND id != ?
            """, (email, customer_id)).fetchone()
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Ese correo pertenece a otro cliente."
                )

        db.execute("""
            UPDATE customers
            SET full_name = ?, email = ?, phone = ?, status = ?
            WHERE id = ?
        """, (full_name, email or None, phone or None, data.status, customer_id))

    return {
        "success": True,
        "message": "Información del cliente actualizada."
    }


class CustomerInteractionCreate(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


@app.post("/api/admin/customers/{customer_id}/interactions")
async def crm_add_interaction(
    customer_id: int,
    data: CustomerInteractionCreate,
    request: Request
):
    admin = get_current_admin(request)

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    message = data.message.strip()
    if len(message) < 2:
        raise HTTPException(status_code=400, detail="La nota es demasiado corta.")

    with get_db() as db:
        customer = db.execute(
            "SELECT id FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.")

        db.execute("""
            INSERT INTO interactions (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'crm')
        """, (
            customer_id,
            message,
            f"Nota registrada por administrador: {admin['username']}"
        ))

    return {
        "success": True,
        "message": "Seguimiento registrado correctamente."
    }


# ========================================================
# ETAPA 7A - ERP: RESERVACIONES
# ========================================================

@app.get("/admin/reservaciones")
async def erp_reservations_page(request: Request):
    admin = get_current_admin(request)

    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_appointments.html",
        context={
            "title": "Reservaciones | MediBot 360",
            "admin": admin
        }
    )


@app.get("/api/admin/appointments")
async def erp_list_appointments(
    request: Request,
    search: str = Query(default="", max_length=100),
    status: str = Query(default=""),
    appointment_date: str = Query(default="", max_length=10)
):
    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    if status not in {"", "confirmed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Estado no válido.")

    if appointment_date:
        try:
            date.fromisoformat(appointment_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha no válida.")

    filters = []
    params = []
    search = search.strip()

    if search:
        filters.append("""
            (
                c.full_name LIKE ?
                OR a.folio LIKE ?
                OR sp.name LIKE ?
                OR p.full_name LIKE ?
            )
        """)
        search_pattern = f"%{search}%"
        params.extend([search_pattern] * 4)

    if status:
        filters.append("a.status = ?")
        params.append(status)

    if appointment_date:
        filters.append("s.appointment_date = ?")
        params.append(appointment_date)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    with get_db() as db:
        appointments = db.execute(f"""
            SELECT
                a.id,
                a.folio,
                a.status,
                p.id AS professional_id,
                sp.id AS specialty_id,
                a.created_at,
                c.full_name AS customer_name,
                c.email AS customer_email,
                c.phone AS customer_phone,
                sp.name AS specialty_name,
                sp.price,
                p.full_name AS professional_name,
                s.appointment_date,
                s.start_time,
                s.end_time
            FROM appointments a
            INNER JOIN customers c ON a.customer_id = c.id
            INNER JOIN professionals p ON a.professional_id = p.id
            INNER JOIN specialties sp ON p.specialty_id = sp.id
            INNER JOIN schedules s ON a.schedule_id = s.id
            {where_clause}
            ORDER BY s.appointment_date DESC, s.start_time DESC, a.id DESC
        """, params).fetchall()

    return {
        "success": True,
        "total": len(appointments),
        "data": [dict(appointment) for appointment in appointments]
    }


@app.post("/api/admin/appointments/{appointment_id}/cancel")
async def erp_cancel_appointment(
    appointment_id: int,
    request: Request
):
    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    with get_db() as db:
        appointment = db.execute("""
            SELECT id, customer_id, schedule_id, status, folio
            FROM appointments
            WHERE id = ?
        """, (appointment_id,)).fetchone()

        if not appointment:
            raise HTTPException(
                status_code=404,
                detail="Reservación no encontrada."
            )

        if appointment["status"] != "confirmed":
            raise HTTPException(
                status_code=409,
                detail="La reservación ya fue cancelada."
            )

        payment_pending_refund = db.execute("""
            SELECT 1
            FROM payments
            WHERE appointment_id = ?
              AND status = 'paid'
            LIMIT 1
        """, (appointment_id,)).fetchone()

        if payment_pending_refund:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La cita tiene un pago registrado. "
                    "Registra primero su devolución simulada."
                )
            )

        updated_appointment = db.execute("""
            UPDATE appointments
            SET status = 'cancelled'
            WHERE id = ? AND status = 'confirmed'
        """, (appointment_id,))

        if updated_appointment.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="La reservación ya fue cancelada."
            )

        updated_schedule = db.execute("""
            UPDATE schedules
            SET status = 'available'
            WHERE id = ? AND status = 'reserved'
        """, (appointment["schedule_id"],))

        if updated_schedule.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="El horario no se pudo liberar."
            )

        db.execute("""
            INSERT INTO interactions
            (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'crm')
        """, (
            appointment["customer_id"],
            f"Reservación cancelada: {appointment['folio']}",
            "Cancelación realizada desde el ERP."
        ))

    return {
        "success": True,
        "message": "Reservación cancelada y horario liberado."
    }


# ===================================================
# ETAPA 7B - REPROGRAMAR RESERVACIONES
# ===================================================

class RescheduleAppointmentRequest(BaseModel):
    schedule_id: int = Field(gt=0)


def validate_reschedule_date(value: str) -> date:
    try:
        selected = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Fecha inválida. Utiliza YYYY-MM-DD."
        )

    today = date.today()

    if not (today < selected <= today + timedelta(days=14)):
        raise HTTPException(
            status_code=400,
            detail="Selecciona una fecha entre mañana y los próximos 14 días."
        )

    if selected.weekday() == 6:
        raise HTTPException(
            status_code=400,
            detail="No hay citas los domingos."
        )

    return selected


@app.get("/api/admin/appointments/{appointment_id}/reschedule-options")
async def erp_reschedule_options(
    appointment_id: int,
    request: Request,
    professional_id: int,
    appointment_date: str = Query(default="", max_length=10)
):
    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    selected_date = validate_reschedule_date(appointment_date)

    with get_db() as db:
        appointment = db.execute("""
            SELECT a.id, a.status, p.specialty_id
            FROM appointments a
            INNER JOIN professionals p ON a.professional_id = p.id
            WHERE a.id = ?
        """, (appointment_id,)).fetchone()

        if not appointment:
            raise HTTPException(
                status_code=404,
                detail="Reservación no encontrada."
            )

        if appointment["status"] != "confirmed":
            raise HTTPException(
                status_code=409,
                detail="Solo se pueden reprogramar reservaciones confirmadas."
            )

        professional = db.execute("""
            SELECT id
            FROM professionals
            WHERE id = ?
              AND specialty_id = ?
              AND active = 1
              AND EXISTS (
                  SELECT 1
                  FROM specialties
                  WHERE id = professionals.specialty_id
                    AND active = 1
              )
        """, (professional_id, appointment["specialty_id"])).fetchone()

        if not professional:
            raise HTTPException(
                status_code=400,
                detail="El profesional debe pertenecer a la misma especialidad."
            )

        schedules = db.execute("""
            SELECT id, professional_id, appointment_date, start_time, end_time
            FROM schedules
            WHERE professional_id = ?
              AND appointment_date = ?
              AND status = 'available'
              AND NOT EXISTS (
                  SELECT 1
                  FROM schedule_day_settings ds
                  WHERE ds.professional_id = s.professional_id
                    AND ds.appointment_date = s.appointment_date
                    AND ds.is_closed = 1
              )
            ORDER BY start_time
        """, (professional_id, selected_date.isoformat())).fetchall()

    return {
        "success": True,
        "total": len(schedules),
        "data": [dict(schedule) for schedule in schedules]
    }


@app.post("/api/admin/appointments/{appointment_id}/reschedule")
async def erp_reschedule_appointment(
    appointment_id: int,
    data: RescheduleAppointmentRequest,
    request: Request
):
    admin = get_current_admin(request)

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    with get_db() as db:
        appointment = db.execute("""
            SELECT
                a.id,
                a.folio,
                a.customer_id,
                a.schedule_id,
                a.professional_id,
                a.status,
                p.specialty_id
            FROM appointments a
            INNER JOIN professionals p ON a.professional_id = p.id
            WHERE a.id = ?
        """, (appointment_id,)).fetchone()

        if not appointment:
            raise HTTPException(
                status_code=404,
                detail="Reservación no encontrada."
            )

        if appointment["status"] != "confirmed":
            raise HTTPException(
                status_code=409,
                detail="Solo se pueden reprogramar reservaciones confirmadas."
            )

        new_schedule = db.execute("""
            SELECT
                s.id,
                s.professional_id,
                s.appointment_date,
                s.status,
                p.specialty_id,
                p.active AS professional_active,
                sp.active AS specialty_active
            FROM schedules s
            INNER JOIN professionals p ON s.professional_id = p.id
            INNER JOIN specialties sp ON p.specialty_id = sp.id
            WHERE s.id = ?
        """, (data.schedule_id,)).fetchone()

        if not new_schedule:
            raise HTTPException(
                status_code=404,
                detail="El nuevo horario no existe."
            )

        if (
            not new_schedule["professional_active"]
            or not new_schedule["specialty_active"]
        ):
            raise HTTPException(
                status_code=409,
                detail="El nuevo servicio o profesional no está disponible."
            )

        validate_reschedule_date(new_schedule["appointment_date"])

        if new_schedule["specialty_id"] != appointment["specialty_id"]:
            raise HTTPException(
                status_code=400,
                detail="El nuevo profesional debe pertenecer a la misma especialidad."
            )

        if new_schedule["status"] != "available":
            raise HTTPException(
                status_code=409,
                detail="El nuevo horario ya no está disponible."
            )

        if is_schedule_day_closed(
            db,
            new_schedule["professional_id"],
            new_schedule["appointment_date"]
        ):
            raise HTTPException(
                status_code=409,
                detail="No puedes reprogramar una cita a un día cerrado."
            )

        released = db.execute("""
            UPDATE schedules
            SET status = 'available'
            WHERE id = ? AND status = 'reserved'
        """, (appointment["schedule_id"],))

        if released.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="El horario actual no se pudo liberar."
            )

        reserved = db.execute("""
            UPDATE schedules
            SET status = 'reserved'
            WHERE id = ? AND status = 'available'
        """, (data.schedule_id,))

        if reserved.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="El nuevo horario ya no está disponible."
            )

        updated_appointment = db.execute("""
            UPDATE appointments
            SET schedule_id = ?, professional_id = ?
            WHERE id = ? AND status = 'confirmed'
        """, (
            data.schedule_id,
            new_schedule["professional_id"],
            appointment_id
        ))

        if updated_appointment.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="La reservación cambió mientras se procesaba."
            )

        db.execute("""
            INSERT INTO interactions
            (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'crm')
        """, (
            appointment["customer_id"],
            f"Reservación reprogramada: {appointment['folio']}",
            f"Nuevo horario: {new_schedule['appointment_date']} "
            f"(administrador: {admin['username']})."
        ))

    return {
        "success": True,
        "message": "Reservación reprogramada correctamente."
    }


# =====================================================
# ETAPA 7E - PAGOS SIMULADOS Y RECURSOS
# =====================================================

class ResourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=500)
    quantity: int = Field(ge=0, le=1000000)
    status: Literal["available", "unavailable"] = "available"


class ResourceUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=500)
    status: Literal["available", "unavailable"]


class StockAdjustment(BaseModel):
    quantity_change: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=3, max_length=200)


def require_operations_admin(request: Request):
    admin = get_current_admin(request)
    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )
    return admin


@app.get("/admin/operaciones")
async def erp_operations_page(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(
            url="/admin/login",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="admin_operations.html",
        context={
            "title": "Pagos y recursos | MediBot 360",
            "admin": admin
        }
    )


@app.get("/api/admin/finance")
async def erp_finance_list(request: Request):
    require_operations_admin(request)

    with get_db() as db:
        rows = db.execute("""
            SELECT
                a.id AS appointment_id,
                a.folio,
                a.status AS appointment_status,
                a.agreed_price AS agreed_price,
                c.full_name AS customer_name,
                sp.name AS specialty_name,
                s.appointment_date,
                p.id AS payment_id,
                p.amount AS payment_amount,
                COALESCE(p.status, 'unpaid') AS payment_status,
                p.payment_date,
                p.refunded_at
            FROM appointments a
            JOIN customers c ON c.id = a.customer_id
            JOIN professionals pr ON pr.id = a.professional_id
            JOIN specialties sp ON sp.id = pr.specialty_id
            JOIN schedules s ON s.id = a.schedule_id
            LEFT JOIN payments p ON p.id = (
                SELECT p2.id
                FROM payments p2
                WHERE p2.appointment_id = a.id
                ORDER BY p2.id DESC
                LIMIT 1
            )
            ORDER BY a.id DESC
        """).fetchall()

    records = [dict(row) for row in rows]
    paid_total = sum(
        float(r["payment_amount"] or 0)
        for r in records
        if r["payment_status"] == "paid"
    )
    pending_total = sum(
        float(r["agreed_price"] or 0)
        for r in records
        if r["appointment_status"] == "confirmed"
        and r["payment_status"] in ("unpaid", "pending")
    )
    refunded_total = sum(
        float(r["payment_amount"] or 0)
        for r in records
        if r["payment_status"] == "refunded"
    )

    return {
        "success": True,
        "data": records,
        "stats": {
            "appointments": len(records),
            "paid_total": round(paid_total, 2),
            "pending_total": round(pending_total, 2),
            "refunded_total": round(refunded_total, 2)
        }
    }


@app.post("/api/admin/payments/{appointment_id}/collect")
async def erp_collect_payment(
    appointment_id: int,
    request: Request
):
    admin = require_operations_admin(request)

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        appointment = db.execute("""
            SELECT id, folio, customer_id, status, agreed_price
            FROM appointments
            WHERE id = ?
        """, (appointment_id,)).fetchone()

        if not appointment:
            raise HTTPException(404, "Reservación no encontrada.")
        if appointment["status"] != "confirmed":
            raise HTTPException(
                409,
                "Solo puedes cobrar citas confirmadas."
            )

        amount = round(
            float(appointment["agreed_price"] or 0),
            2
        )
        if amount <= 0:
            raise HTTPException(
                409,
                "La reservación no tiene un importe válido."
            )

        existing = db.execute("""
            SELECT id, status
            FROM payments
            WHERE appointment_id = ?
        """, (appointment_id,)).fetchall()

        if len(existing) > 1:
            raise HTTPException(
                409,
                "Existen pagos duplicados. Revisa este registro."
            )
        if existing:
            if existing[0]["status"] != "pending":
                raise HTTPException(
                    409,
                    "Esta cita ya tiene un pago registrado."
                )

            db.execute("""
                UPDATE payments
                SET amount = ?,
                    status = 'paid',
                    payment_date = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (amount, existing[0]["id"]))
        else:
            db.execute("""
                INSERT INTO payments
                    (appointment_id, amount, status, payment_date)
                VALUES (?, ?, 'paid', CURRENT_TIMESTAMP)
            """, (appointment_id, amount))

        db.execute("""
            INSERT INTO interactions
                (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'erp')
        """, (
            appointment["customer_id"],
            f"Pago simulado del folio {appointment['folio']}",
            f"Importe ${amount:.2f} MXN. "
            f"Registrado por {admin['username']}"
        ))

    return {
        "success": True,
        "message": "Pago simulado registrado correctamente."
    }


@app.post("/api/admin/payments/{appointment_id}/refund")
async def erp_refund_payment(
    appointment_id: int,
    request: Request
):
    admin = require_operations_admin(request)

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        payment = db.execute("""
            SELECT
                p.id,
                p.amount,
                p.status,
                a.customer_id,
                a.folio
            FROM payments p
            JOIN appointments a ON a.id = p.appointment_id
            WHERE p.appointment_id = ?
            ORDER BY p.id DESC
            LIMIT 1
        """, (appointment_id,)).fetchone()

        if not payment:
            raise HTTPException(
                404,
                "Esta cita no tiene un pago registrado."
            )
        if payment["status"] != "paid":
            raise HTTPException(
                409,
                "El pago no admite una devolución."
            )

        updated = db.execute("""
            UPDATE payments
            SET status = 'refunded',
                refunded_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'paid'
        """, (payment["id"],))

        if updated.rowcount != 1:
            raise HTTPException(
                409,
                "No se pudo registrar la devolución."
            )

        db.execute("""
            INSERT INTO interactions
                (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'erp')
        """, (
            payment["customer_id"],
            f"Devolución simulada del folio {payment['folio']}",
            f"Importe ${payment['amount']:.2f} MXN. "
            f"Registrada por {admin['username']}"
        ))

    return {
        "success": True,
        "message": "Devolución simulada registrada."
    }


@app.get("/api/admin/resources")
async def erp_resources_list(request: Request):
    require_operations_admin(request)

    with get_db() as db:
        resources = db.execute("""
            SELECT id, name, description, quantity, status
            FROM resources
            ORDER BY name, id
        """).fetchall()

        movements = db.execute("""
            SELECT
                rm.id,
                rm.resource_id,
                r.name AS resource_name,
                rm.quantity_change,
                rm.reason,
                rm.created_at,
                u.username
            FROM resource_movements rm
            JOIN resources r ON r.id = rm.resource_id
            LEFT JOIN users u ON u.id = rm.user_id
            ORDER BY rm.id DESC
            LIMIT 30
        """).fetchall()

    return {
        "success": True,
        "data": [dict(r) for r in resources],
        "movements": [dict(m) for m in movements]
    }


@app.post("/api/admin/resources", status_code=201)
async def erp_create_resource(
    data: ResourceCreate,
    request: Request
):
    admin = require_operations_admin(request)
    name = data.name.strip()
    description = data.description.strip()

    if len(name) < 2:
        raise HTTPException(400, "Nombre de recurso inválido.")

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        duplicate = db.execute("""
            SELECT id
            FROM resources
            WHERE LOWER(name) = LOWER(?)
        """, (name,)).fetchone()

        if duplicate:
            raise HTTPException(
                409,
                "Este recurso ya está registrado."
            )

        created = db.execute("""
            INSERT INTO resources
                (name, description, quantity, status)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            description,
            data.quantity,
            data.status
        ))

        if data.quantity > 0:
            db.execute("""
                INSERT INTO resource_movements
                    (resource_id, user_id,
                     quantity_change, reason)
                VALUES (?, ?, ?, ?)
            """, (
                created.lastrowid,
                admin["id"],
                data.quantity,
                "Existencia inicial"
            ))

    return {
        "success": True,
        "message": "Recurso registrado correctamente."
    }


@app.put("/api/admin/resources/{resource_id}")
async def erp_update_resource(
    resource_id: int,
    data: ResourceUpdate,
    request: Request
):
    require_operations_admin(request)
    name = data.name.strip()
    description = data.description.strip()

    if len(name) < 2:
        raise HTTPException(400, "Nombre de recurso inválido.")

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("""
            SELECT id
            FROM resources
            WHERE id = ?
        """, (resource_id,)).fetchone()

        if not existing:
            raise HTTPException(
                404,
                "Recurso no encontrado."
            )

        duplicate = db.execute("""
            SELECT id
            FROM resources
            WHERE LOWER(name) = LOWER(?)
              AND id <> ?
        """, (name, resource_id)).fetchone()

        if duplicate:
            raise HTTPException(
                409,
                "Ya existe un recurso con ese nombre."
            )

        db.execute("""
            UPDATE resources
            SET name = ?, description = ?, status = ?
            WHERE id = ?
        """, (
            name,
            description,
            data.status,
            resource_id
        ))

    return {
        "success": True,
        "message": "Recurso actualizado correctamente."
    }


@app.post("/api/admin/resources/{resource_id}/adjust")
async def erp_adjust_resource(
    resource_id: int,
    data: StockAdjustment,
    request: Request
):
    admin = require_operations_admin(request)
    reason = data.reason.strip()

    if data.quantity_change == 0:
        raise HTTPException(
            400,
            "El movimiento debe cambiar la cantidad."
        )
    if len(reason) < 3:
        raise HTTPException(
            400,
            "Escribe un motivo válido."
        )

    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        resource = db.execute("""
            SELECT id, quantity
            FROM resources
            WHERE id = ?
        """, (resource_id,)).fetchone()

        if not resource:
            raise HTTPException(
                404,
                "Recurso no encontrado."
            )

        new_quantity = (
            resource["quantity"] + data.quantity_change
        )
        if not 0 <= new_quantity <= 1000000:
            raise HTTPException(
                409,
                "La cantidad resultante no es válida."
            )

        db.execute("""
            UPDATE resources
            SET quantity = ?
            WHERE id = ?
        """, (new_quantity, resource_id))

        db.execute("""
            INSERT INTO resource_movements
                (resource_id, user_id,
                 quantity_change, reason)
            VALUES (?, ?, ?, ?)
        """, (
            resource_id,
            admin["id"],
            data.quantity_change,
            reason
        ))

    return {
        "success": True,
        "quantity": new_quantity,
        "message": "Movimiento registrado correctamente."
    }


# =========================================================
# ETAPA 7D - ADMINISTRACIÓN DE HORARIOS
# =========================================================

class ScheduleCreate(BaseModel):
    professional_id: int = Field(gt=0)
    appointment_date: str
    start_time: str
    end_time: str
    status: Literal["available", "blocked"] = "available"


class ScheduleUpdate(BaseModel):
    start_time: str
    end_time: str
    status: Literal["available", "blocked"]


class ScheduleDayUpdate(BaseModel):
    is_closed: bool


def validate_schedule_times(start: str, end: str):
    pattern = r"(?:[01]\d|2[0-3]):[0-5]\d"
    if not re.fullmatch(pattern, start) or not re.fullmatch(pattern, end):
        raise HTTPException(
            status_code=400,
            detail="Las horas deben tener el formato HH:MM."
        )
    if start >= end:
        raise HTTPException(
            status_code=400,
            detail="La hora de término debe ser posterior al inicio."
        )


def validate_schedule_management_date(value: str) -> date:
    try:
        selected = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Fecha inválida. Utiliza YYYY-MM-DD."
        )

    today = date.today()
    if not (today < selected <= today + timedelta(days=14)):
        raise HTTPException(
            status_code=400,
            detail="Selecciona una fecha entre mañana y los próximos 14 días."
        )
    if selected.weekday() == 6:
        raise HTTPException(
            status_code=400,
            detail="No se pueden administrar horarios los domingos."
        )
    return selected


def ensure_schedule_has_no_overlap(
    db,
    professional_id: int,
    appointment_date: str,
    start_time: str,
    end_time: str,
    exclude_id: int | None = None
):
    params = [professional_id, appointment_date, end_time, start_time]
    exclusion = ""
    if exclude_id is not None:
        exclusion = "AND id != ?"
        params.append(exclude_id)

    overlap = db.execute(f"""
        SELECT 1
        FROM schedules
        WHERE professional_id = ?
          AND appointment_date = ?
          AND start_time < ?
          AND end_time > ?
          {exclusion}
        LIMIT 1
    """, params).fetchone()

    if overlap:
        raise HTTPException(
            status_code=409,
            detail="El horario se superpone con otro turno."
        )


@app.get("/admin/horarios")
async def admin_schedules_page(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_schedules.html",
        context={
            "title": "Horarios | MediBot 360",
            "admin": admin
        }
    )


@app.get("/api/admin/schedule-management")
async def admin_get_schedule_management(
    request: Request,
    professional_id: int,
    appointment_date: str = Query(max_length=10)
):
    require_admin(request)
    validate_schedule_management_date(appointment_date)

    with get_db() as db:
        professional = db.execute("""
            SELECT id
            FROM professionals
            WHERE id = ?
        """, (professional_id,)).fetchone()
        if not professional:
            raise HTTPException(
                status_code=404,
                detail="El profesional no existe."
            )

        schedules = db.execute("""
            SELECT
                s.id,
                s.professional_id,
                s.appointment_date,
                s.start_time,
                s.end_time,
                s.status,
                a.folio
            FROM schedules s
            LEFT JOIN appointments a
                ON a.schedule_id = s.id
            WHERE s.professional_id = ?
              AND s.appointment_date = ?
            ORDER BY s.start_time
        """, (professional_id, appointment_date)).fetchall()

        is_closed = is_schedule_day_closed(
            db, professional_id, appointment_date
        )

    return {
        "success": True,
        "is_closed": is_closed,
        "data": [dict(schedule) for schedule in schedules]
    }


@app.post("/api/admin/manage-schedules")
async def admin_create_schedule(data: ScheduleCreate, request: Request):
    require_admin(request)
    selected_date = validate_schedule_management_date(data.appointment_date)
    validate_schedule_times(data.start_time, data.end_time)

    with get_db() as db:
        if is_schedule_day_closed(
            db, data.professional_id, selected_date.isoformat()
        ):
            raise HTTPException(
                status_code=409,
                detail="No puedes agregar horarios a un día cerrado."
            )

        professional = db.execute("""
            SELECT id
            FROM professionals
            WHERE id = ? AND active = 1
        """, (data.professional_id,)).fetchone()
        if not professional:
            raise HTTPException(
                status_code=404,
                detail="El profesional no existe o está inactivo."
            )

        ensure_schedule_has_no_overlap(
            db,
            data.professional_id,
            selected_date.isoformat(),
            data.start_time,
            data.end_time
        )

        try:
            cursor = db.execute("""
                INSERT INTO schedules
                (professional_id, appointment_date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?)
            """, (
                data.professional_id,
                selected_date.isoformat(),
                data.start_time,
                data.end_time,
                data.status
            ))
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="Ya existe un horario con ese inicio."
            )

    return {
        "success": True,
        "message": "Horario creado correctamente.",
        "schedule_id": cursor.lastrowid
    }


@app.put("/api/admin/manage-schedules/{schedule_id}")
async def admin_update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    request: Request
):
    require_admin(request)
    validate_schedule_times(data.start_time, data.end_time)

    with get_db() as db:
        schedule = db.execute("""
            SELECT id, professional_id, appointment_date, status
            FROM schedules
            WHERE id = ?
        """, (schedule_id,)).fetchone()
        if not schedule:
            raise HTTPException(status_code=404, detail="El horario no existe.")

        appointment = db.execute("""
            SELECT 1
            FROM appointments
            WHERE schedule_id = ?
            LIMIT 1
        """, (schedule_id,)).fetchone()
        if appointment:
            raise HTTPException(
                status_code=409,
                detail="No puedes modificar un horario con historial de citas."
            )

        if is_schedule_day_closed(
            db, schedule["professional_id"], schedule["appointment_date"]
        ):
            raise HTTPException(
                status_code=409,
                detail="No puedes modificar horarios de un día cerrado."
            )

        ensure_schedule_has_no_overlap(
            db,
            schedule["professional_id"],
            schedule["appointment_date"],
            data.start_time,
            data.end_time,
            schedule_id
        )
        db.execute("""
            UPDATE schedules
            SET start_time = ?, end_time = ?, status = ?
            WHERE id = ?
        """, (data.start_time, data.end_time, data.status, schedule_id))

    return {"success": True, "message": "Horario actualizado correctamente."}


@app.put("/api/admin/schedule-days/{professional_id}/{appointment_date}")
async def admin_update_schedule_day(
    professional_id: int,
    appointment_date: str,
    data: ScheduleDayUpdate,
    request: Request
):
    require_admin(request)
    selected_date = validate_schedule_management_date(appointment_date)

    with get_db() as db:
        professional = db.execute("""
            SELECT id
            FROM professionals
            WHERE id = ?
        """, (professional_id,)).fetchone()
        if not professional:
            raise HTTPException(status_code=404, detail="El profesional no existe.")

        if data.is_closed:
            confirmed = db.execute("""
                SELECT 1
                FROM appointments a
                INNER JOIN schedules s ON s.id = a.schedule_id
                WHERE a.professional_id = ?
                  AND s.appointment_date = ?
                  AND a.status = 'confirmed'
                LIMIT 1
            """, (professional_id, selected_date.isoformat())).fetchone()
            if confirmed:
                raise HTTPException(
                    status_code=409,
                    detail="No puedes cerrar un día con citas confirmadas."
                )

        db.execute("""
            INSERT INTO schedule_day_settings
                (professional_id, appointment_date, is_closed)
            VALUES (?, ?, ?)
            ON CONFLICT(professional_id, appointment_date)
            DO UPDATE SET is_closed = excluded.is_closed
        """, (
            professional_id,
            selected_date.isoformat(),
            int(data.is_closed)
        ))

    return {
        "success": True,
        "message": (
            "Día bloqueado correctamente."
            if data.is_closed else "Día reabierto correctamente."
        )
    }


# =====================================================
# ETAPA 8 - CHATBOT DE RECEPCION VIRTUAL
# =====================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ChatAppointmentProof(BaseModel):
    folio: str = Field(min_length=11, max_length=20)
    email: str = Field(min_length=5, max_length=150)
    phone: str = Field(min_length=10, max_length=20)


def normalize_chat(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower())
    return "".join(
        letter for letter in plain
        if not unicodedata.combining(letter)
    )


@app.post("/api/chat")
async def chatbot_reply(data: ChatRequest):
    message = normalize_chat(data.message.strip())
    action = None
    options = [
        "Servicios y precios",
        "Reservar cita",
        "Consultar mi cita",
        "Cancelar mi cita"
    ]

    if any(word in message for word in (
        "emergencia",
        "urgencia",
        "dolor de pecho",
        "no puedo respirar",
        "falta de aire",
        "convulsion",
        "hemorragia",
        "desmayo"
    )):
        reply = (
            "Si se trata de una emergencia, llama al "
            "911 en México o acude a urgencias. "
            "Este asistente no realiza diagnósticos."
        )
    elif any(word in message for word in (
        "cancelar", "anular", "cancelacion"
    )):
        reply = (
            "Para cancelar una cita, verifica tu folio, "
            "correo y teléfono de registro."
        )
        action = "cancel"
    elif any(word in message for word in (
        "consultar mi cita",
        "consultar cita",
        "consultar reservacion",
        "consultar folio",
        "mi folio",
        "mi cita",
        "buscar folio",
        "ver cita"
    )):
        reply = (
            "Para consultar tu cita, verifica tu folio, "
            "correo y teléfono de registro."
        )
        action = "lookup"
    elif any(word in message for word in (
        "reservar",
        "agendar",
        "apartar",
        "sacar cita",
        "solicitar cita"
    )):
        reply = (
            "Puedes reservar aquí mismo. Elige "
            "especialidad, profesional, fecha y horario."
        )
        action = "booking"
    elif any(word in message for word in (
        "horario",
        "disponibilidad",
        "cuando atienden"
    )):
        reply = (
            "Los horarios dependen del profesional "
            "y del día. Para ver los turnos libres, "
            "abre Reservar cita y selecciona una fecha."
        )
    else:
        with get_db() as db:
            services = db.execute("""
                SELECT name, price
                FROM specialties
                WHERE active = 1
                ORDER BY name
            """).fetchall()

        selected = [
            service for service in services
            if normalize_chat(service["name"]) in message
        ]

        if any(word in message for word in (
            "precio",
            "costo",
            "cuanto",
            "especialidad",
            "servicio",
            "cardiologia",
            "dermatologia",
            "pediatria",
            "nutricion",
            "psicologia",
            "medicina general"
        )):
            show = selected or services
            reply = (
                "Servicios de demostración (MXN):\n"
                + "\n".join(
                    f"• {service['name']}: "
                    f"${float(service['price']):,.2f}"
                    for service in show
                )
            )
        elif any(word in message for word in (
            "hola", "buenas", "ayuda", "menu"
        )):
            reply = (
                "Hola, soy el asistente de MediBot 360. "
                "Puedo mostrar servicios y precios, "
                "agendar o consultar y cancelar citas."
            )
        else:
            reply = (
                "Puedo ayudarte con servicios, precios, "
                "horarios y reservaciones. "
                "Elige una opción para continuar."
            )

    return {
        "success": True,
        "reply": reply,
        "action": action,
        "options": options
    }


def find_verified_chat_appointment(
    db,
    credentials: ChatAppointmentProof
):
    error = HTTPException(
        404,
        "No se pudo verificar la reservación con esos datos."
    )

    folio = credentials.folio.strip().upper()
    if not re.fullmatch(r"MB-[0-9A-F]{8}", folio):
        raise error

    email = credentials.email.strip().lower()
    phone = re.sub(r"\D", "", credentials.phone)
    if len(phone) < 10 or "@" not in email:
        raise error

    row = db.execute("""
        SELECT
            a.id,
            a.folio,
            a.customer_id,
            a.status,
            a.schedule_id,
            c.email,
            c.phone,
            sp.name AS specialty_name,
            p.full_name AS professional_name,
            s.appointment_date,
            s.start_time,
            s.status AS schedule_status
        FROM appointments a
        JOIN customers c ON c.id = a.customer_id
        JOIN professionals p ON p.id = a.professional_id
        JOIN specialties sp ON sp.id = p.specialty_id
        JOIN schedules s ON s.id = a.schedule_id
        WHERE a.folio = ?
    """, (folio,)).fetchone()

    if row is None:
        raise error

    stored_email = (
        row["email"] or ""
    ).strip().lower().encode("utf-8")
    entered_email = email.encode("utf-8")
    stored_phone = re.sub(
        r"\D", "", row["phone"] or ""
    ).encode("utf-8")
    entered_phone = phone.encode("utf-8")

    if not (
        hmac.compare_digest(stored_email, entered_email)
        and hmac.compare_digest(stored_phone, entered_phone)
    ):
        raise error

    return row


@app.post("/api/chat/appointments/lookup")
async def chat_lookup_appointment(
    credentials: ChatAppointmentProof,
    request: Request
):
    check_rate_limit(
        request, "chat_verification", maximum=8
    )
    with get_db() as db:
        appointment = find_verified_chat_appointment(db, credentials)

    return {
        "success": True,
        "data": {
            "folio": appointment["folio"],
            "status": appointment["status"],
            "specialty": appointment["specialty_name"],
            "professional": appointment["professional_name"],
            "date": appointment["appointment_date"],
            "time": appointment["start_time"]
        }
    }


@app.post("/api/chat/appointments/cancel")
async def chat_cancel_appointment(
    credentials: ChatAppointmentProof,
    request: Request
):
    check_rate_limit(
        request, "chat_verification", maximum=8
    )
    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        appointment = find_verified_chat_appointment(db, credentials)

        if appointment["status"] != "confirmed":
            raise HTTPException(
                409,
                "La cita ya no está confirmada."
            )
        if appointment["schedule_status"] != "reserved":
            raise HTTPException(
                409,
                "El horario requiere revisión administrativa."
            )

        paid = db.execute("""
            SELECT 1
            FROM payments
            WHERE appointment_id = ?
              AND status = 'paid'
            LIMIT 1
        """, (appointment["id"],)).fetchone()

        if paid:
            raise HTTPException(
                409,
                "Esta cita tiene un pago registrado. "
                "Contacta a administración para gestionar "
                "la devolución antes de cancelarla."
            )

        changed = db.execute("""
            UPDATE appointments
            SET status = 'cancelled'
            WHERE id = ?
              AND status = 'confirmed'
        """, (appointment["id"],))

        released = db.execute("""
            UPDATE schedules
            SET status = 'available'
            WHERE id = ?
              AND status = 'reserved'
        """, (appointment["schedule_id"],))

        if changed.rowcount != 1 or released.rowcount != 1:
            raise HTTPException(
                409,
                "No se pudo cancelar la cita."
            )

        db.execute("""
            INSERT INTO interactions
            (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'chatbot')
        """, (
            appointment["customer_id"],
            "Cancelación solicitada por chatbot: "
            + appointment["folio"],
            "Cita cancelada y horario liberado"
        ))

    return {
        "success": True,
        "message": (
            "La reservación fue cancelada. "
            "El horario quedó disponible."
        )
    }


# =========================================================
# ETAPA 9 - DASHBOARD ANALITICO
# =========================================================

@app.get("/api/admin/dashboard/analytics")
async def dashboard_analytics(
    request: Request,
    days: int = Query(default=30, ge=7, le=90)
):
    if days not in (7, 30, 90):
        raise HTTPException(
            status_code=400,
            detail="Selecciona 7, 30 o 90 días."
        )

    if not get_current_admin(request):
        raise HTTPException(
            status_code=401,
            detail="Sesión administrativa requerida."
        )

    today = date.today()
    start = today - timedelta(days=days - 1)
    start_text = start.isoformat()
    end_text = today.isoformat()

    with get_db() as db:
        customer_total = db.execute("""
            SELECT COUNT(*) AS total
            FROM customers
            WHERE substr(created_at, 1, 10)
                  BETWEEN ? AND ?
        """, (start_text, end_text)).fetchone()["total"]

        appointment_stats = db.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(
                    CASE WHEN status = 'confirmed'
                    THEN 1 ELSE 0 END
                ), 0) AS confirmed,
                COALESCE(SUM(
                    CASE WHEN status = 'cancelled'
                    THEN 1 ELSE 0 END
                ), 0) AS cancelled
            FROM appointments
            WHERE substr(created_at, 1, 10)
                  BETWEEN ? AND ?
        """, (start_text, end_text)).fetchone()

        payment_stats = db.execute("""
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN status = 'paid'
                        AND substr(payment_date, 1, 10)
                            BETWEEN ? AND ?
                        THEN amount
                        ELSE 0
                    END
                ), 0) AS paid,
                COALESCE(SUM(
                    CASE
                        WHEN status = 'refunded'
                        AND substr(refunded_at, 1, 10)
                            BETWEEN ? AND ?
                        THEN amount
                        ELSE 0
                    END
                ), 0) AS refunded
            FROM payments
        """, (
            start_text, end_text,
            start_text, end_text
        )).fetchone()

        appointments_daily = db.execute("""
            SELECT
                substr(created_at, 1, 10) AS day,
                COUNT(*) AS total
            FROM appointments
            WHERE substr(created_at, 1, 10)
                  BETWEEN ? AND ?
            GROUP BY substr(created_at, 1, 10)
            ORDER BY day
        """, (start_text, end_text)).fetchall()

        customers_daily = db.execute("""
            SELECT
                substr(created_at, 1, 10) AS day,
                COUNT(*) AS total
            FROM customers
            WHERE substr(created_at, 1, 10)
                  BETWEEN ? AND ?
            GROUP BY substr(created_at, 1, 10)
            ORDER BY day
        """, (start_text, end_text)).fetchall()

        top_specialties = db.execute("""
            SELECT
                sp.name AS specialty,
                COUNT(a.id) AS total
            FROM appointments a
            JOIN professionals p
                ON p.id = a.professional_id
            JOIN specialties sp
                ON sp.id = p.specialty_id
            WHERE substr(a.created_at, 1, 10)
                  BETWEEN ? AND ?
            GROUP BY sp.id, sp.name
            ORDER BY total DESC, sp.name
            LIMIT 6
        """, (start_text, end_text)).fetchall()

        payments_daily = db.execute("""
            SELECT
                substr(payment_date, 1, 10) AS day,
                ROUND(SUM(amount), 2) AS total
            FROM payments
            WHERE status = 'paid'
              AND substr(payment_date, 1, 10)
                  BETWEEN ? AND ?
            GROUP BY substr(payment_date, 1, 10)
            ORDER BY day
        """, (start_text, end_text)).fetchall()

    all_dates = [
        (start + timedelta(days=i)).isoformat()
        for i in range(days)
    ]

    def daily_values(rows):
        values = {
            row["day"]: float(row["total"])
            for row in rows
        }
        return [values.get(day, 0) for day in all_dates]

    return {
        "success": True,
        "period": {
            "days": days,
            "start": start_text,
            "end": end_text
        },
        "summary": {
            "new_customers": customer_total,
            "new_appointments": appointment_stats["total"],
            "confirmed": appointment_stats["confirmed"],
            "cancelled": appointment_stats["cancelled"],
            "paid_amount": round(
                float(payment_stats["paid"]), 2
            ),
            "refunded_amount": round(
                float(payment_stats["refunded"]), 2
            )
        },
        "charts": {
            "dates": all_dates,
            "appointments": daily_values(appointments_daily),
            "customers": daily_values(customers_daily),
            "payments": daily_values(payments_daily),
            "specialties": [
                {
                    "name": row["specialty"],
                    "total": row["total"]
                }
                for row in top_specialties
            ]
        }
    }


# ==================================================
# ETAPA 10B - SEGURIDAD HTTP Y ORIGEN
# ==================================================

@app.middleware("http")
async def medibot_security_middleware(
    request: Request,
    call_next
):
    path = request.url.path
    method = request.method.upper()
    modifying_methods = {"POST", "PUT", "PATCH", "DELETE"}

    protected_action = (
        path.startswith("/api/admin/")
        or path in (
                "/api/auth/login",
                "/api/auth/logout"
        )
    )

    if method in modifying_methods and protected_action:
        source = (
                request.headers.get("origin")
                or request.headers.get("referer")
        )

        if not source:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "No se pudo verificar el origen "
                            "de la solicitud."
                        )
                    }
                )

        parsed = urlsplit(source)
        valid_origin = (
                parsed.scheme == request.url.scheme
                and parsed.netloc.lower()
                    == request.url.netloc.lower()
        )

        if not valid_origin:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Solicitud rechazada: "
                            "origen no autorizado."
                        )
                    }
                )

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    if (
        path.startswith("/admin")
        or path.startswith("/api/admin/")
        or path.startswith("/api/chat/appointments/")
    ):
        response.headers["Cache-Control"] = "no-store"

    return response
