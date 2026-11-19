
import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

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


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=100
    )
    password: str = Field(
        min_length=1,
        max_length=200
    )


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
    https_only=False
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
            ORDER BY start_time
        """, (professional_id, appointment_date)).fetchall()

    return {
        "success": True,
        "total": len(schedules),
        "data": [dict(item) for item in schedules]
    }


@app.post("/api/appointments")
async def create_appointment(appointment: AppointmentRequest):
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
        schedule = db.execute("""
            SELECT id, professional_id, appointment_date, status
            FROM schedules
            WHERE id = ?
        """, (appointment.schedule_id,)).fetchone()

        if schedule is None:
            raise HTTPException(
                status_code=404,
                detail="El horario seleccionado no existe."
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
            (folio, customer_id, professional_id, schedule_id, status)
            VALUES (?, ?, ?, ?, 'confirmed')
        """, (
            folio,
            customer["id"],
            schedule["professional_id"],
            appointment.schedule_id
        ))

        appointment_row = db.execute("""
            SELECT id
            FROM appointments
            WHERE folio = ?
        """, (folio,)).fetchone()

        db.execute("""
            INSERT INTO interactions
            (customer_id, message, response, channel)
            VALUES (?, ?, ?, 'web')
        """, (
            customer["id"],
            "Solicitud de reservación",
            f"Reservación creada con folio {folio}",
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


@app.post("/api/auth/login")
async def login(data: LoginRequest, request: Request):
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
                p.specialty_id
            FROM schedules s
            INNER JOIN professionals p ON s.professional_id = p.id
            WHERE s.id = ?
        """, (data.schedule_id,)).fetchone()

        if not new_schedule:
            raise HTTPException(
                status_code=404,
                detail="El nuevo horario no existe."
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
