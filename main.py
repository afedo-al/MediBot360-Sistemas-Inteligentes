"""MediBot 360: sitio web de una PyME médica ficticia con chatbot, CRM y ERP (todo gratuito y local)."""
import csv
import io
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app import chatbot, services
from app.config import CONTACT_TOPICS
from app.db import BASE_DIR, connect, init_db
from app.security import make_token, read_token, verify_password

PHONE = r"^\d{10}$"
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="MediBot 360", version="2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'"
    return resp


def page(name: str):
    return FileResponse(BASE_DIR / "templates" / name)


@app.get("/", include_in_schema=False)
def admin_home():
    """Entrada principal: panel administrativo (inicio de sesión o dashboard según la sesión)."""
    return page("admin.html")


@app.get("/sitio", include_in_schema=False)
def public_site():
    return page("index.html")


@app.get("/reservar", include_in_schema=False)
def reservar():
    return page("reservar.html")


@app.get("/admin", include_in_schema=False)
def admin_alias():
    return RedirectResponse("/", status_code=308)


def client_id(request: Request) -> str:
    return request.client.host if request.client else ""


# ---------------------------------------------------------------- API pública
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    state: dict = Field(default_factory=dict)
    page: str = Field(default="", max_length=20)
    session: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9-]*$")


class BookIn(BaseModel):
    specialty_id: int
    date: str
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    alias: str = Field(min_length=2, max_length=60)
    phone: str = Field(default="", pattern=r"^(\d{10})?$")
    email: str = Field(default="", max_length=120)
    professional_id: Optional[int] = None


class PinIn(BaseModel):
    pin: str = Field(min_length=1, max_length=12)


@app.get("/api/specialties")
def specialties():
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT s.id,s.name,s.price,s.description,GROUP_CONCAT(p.name,', ') AS professionals "
            "FROM specialties s LEFT JOIN professionals p ON p.specialty_id=s.id AND p.active=1 "
            "WHERE s.active=1 GROUP BY s.id ORDER BY s.id")]


@app.get("/api/slots")
def slots(specialty_id: int, date: str, professional_id: Optional[int] = None, detailed: bool = False):
    """Horarios libres. Con `detailed=true` devuelve todas las opciones reales por especialista."""
    day = services.check_date(date)
    with connect() as db:
        if detailed or professional_id is not None:
            return services.slots_by_professional(db, specialty_id, day, professional_id)
        return [{"time": s["time"], "professional": s["professional"]}
                for s in services.available_slots(db, specialty_id, day)]


@app.get("/api/professionals")
def professionals(specialty_id: Optional[int] = None):
    with connect() as db:
        sql, args = "SELECT id,name,specialty_id FROM professionals WHERE active=1", []
        if specialty_id is not None:
            sql += " AND specialty_id=?"
            args.append(specialty_id)
        return [dict(r) for r in db.execute(sql + " ORDER BY id", args)]


@app.get("/api/next-available")
def next_available():
    """Próximo horario libre por especialidad (alimenta la portada y el asistente)."""
    with connect() as db:
        out = []
        for s in db.execute("SELECT id,name,price FROM specialties WHERE active=1 ORDER BY id").fetchall():
            nxt = services.next_available(db, s["id"])
            out.append({"specialty_id": s["id"], "specialty": s["name"], "price": s["price"],
                        "date": nxt["date"] if nxt else None, "time": nxt["time"] if nxt else None,
                        "professional": nxt["professional"] if nxt else None})
        return out


def _check_email(email: str):
    if email and not re.match(EMAIL, email):
        raise HTTPException(422, "Correo inválido")


@app.post("/api/appointments", status_code=201)
def create_appointment(data: BookIn):
    """Crea la cita y devuelve folio + PIN privado (el PIN solo se muestra en esta respuesta)."""
    _check_email(data.email)
    with connect() as db:
        return services.book_appointment(db, data.specialty_id, data.date, data.time, data.alias.strip(),
                                         data.phone, data.email, professional_id=data.professional_id)


@app.get("/api/appointments/{code}")
def get_appointment(code: str, pin: str, request: Request):
    with connect() as db:
        return services.get_appointment_public(db, code, pin, client_id(request))


@app.get("/api/appointments/{code}/ics")
def appointment_ics(code: str, pin: str, request: Request):
    """Archivo de calendario (.ics) para que el paciente agregue su cita a Google/Outlook/iPhone."""
    with connect() as db:
        a = services.get_appointment_public(db, code, pin, client_id(request))
    start = datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M")
    fmt = "%Y%m%dT%H%M%S"
    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MediBot 360//Agenda//ES", "BEGIN:VEVENT",
        f"UID:{a['code']}@medibot360", f"DTSTAMP:{datetime.now().strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}", f"DTEND:{(start + timedelta(hours=1)).strftime(fmt)}",
        f"SUMMARY:Cita de {a['specialty']} - MediBot 360",
        f"DESCRIPTION:Folio {a['code']} con {a['professional']}. Estado: {a['status']}.",
        "LOCATION:MediBot 360\\, Centro Histórico\\, San Francisco de Campeche",
        "END:VEVENT", "END:VCALENDAR", ""])
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="cita-{a["code"]}.ics"'})


@app.post("/api/appointments/{code}/cancel")
def cancel(code: str, data: PinIn, request: Request):
    with connect() as db:
        return services.cancel_appointment(db, code, data.pin, client_id(request))


@app.post("/api/chat")
def chat(data: ChatIn):
    session = data.session or "anon"
    with connect() as db:
        out = chatbot.handle(db, data.message, data.state if isinstance(data.state, dict) else {},
                             page=data.page, session=session)
        db.execute("INSERT INTO chat_logs(intent) VALUES(?)", (out["intent"],))
        # Métricas operativas anónimas: identificador aleatorio de conversación, sin texto ni datos personales
        # (salvo la versión anonimizada de mensajes no comprendidos, sin dígitos ni correos).
        db.executemany("INSERT INTO chat_events(session,event,detail) VALUES(?,?,?)",
                       [(session, "message", out["intent"])] +
                       [(session, ev, str(detail)[:80]) for ev, detail in out.pop("events", [])])
    return out


@app.get("/api/stats")
def stats():
    with connect() as db:
        rows = db.execute("SELECT status,COUNT(*) n FROM appointments GROUP BY status").fetchall()
        return {"appointments": {r["status"]: r["n"] for r in rows},
                "total": sum(r["n"] for r in rows)}


# ---------------------------------------------------------------------- Auth
_failures: dict[str, list[float]] = {}


class LoginIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=100)


def current_user(request: Request) -> dict:
    data = read_token(request.cookies.get("mb_session"))
    if not data:
        raise HTTPException(401, "Inicia sesión")
    return data


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["r"] != "admin":
        raise HTTPException(403, "Se requiere rol administrador")
    return user


def audit(db, user: dict, action: str):
    db.execute("INSERT INTO audit_log(username,action) VALUES(?,?)", (user["u"], action))


@app.post("/api/admin/login")
def login(data: LoginIn, response: Response):
    key = data.username.lower()
    recent = [t for t in _failures.get(key, []) if time.time() - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Demasiados intentos. Espera 5 minutos.")
    with connect() as db:
        u = db.execute("SELECT * FROM users WHERE username=?", (data.username,)).fetchone()
        if not u or not verify_password(data.password, u["password_hash"]):
            _failures[key] = recent + [time.time()]
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        _failures.pop(key, None)
        audit(db, {"u": u["username"]}, "inicio de sesión")
    response.set_cookie("mb_session", make_token(u["username"], u["role"]), httponly=True, samesite="strict",
                        max_age=8 * 3600)
    return {"username": u["username"], "role": u["role"]}


@app.post("/api/admin/logout")
def logout(response: Response):
    response.delete_cookie("mb_session")
    return {"ok": True}


@app.get("/api/admin/me")
def me(user: dict = Depends(current_user)):
    return {"username": user["u"], "role": user["r"]}


# ----------------------------------------------------------------------- CRM
class CustomerIn(BaseModel):
    alias: str = Field(min_length=2, max_length=60)
    phone: str = Field(default="", pattern=r"^(\d{10})?$")
    email: str = Field(default="", max_length=120)
    stage: Literal["prospecto", "contactado", "cliente", "inactivo"] = "prospecto"
    source: str = Field(default="manual", max_length=30)
    notes: str = Field(default="", max_length=500)


class CustomerPatch(BaseModel):
    alias: Optional[str] = Field(default=None, min_length=2, max_length=60)
    phone: Optional[str] = Field(default=None, pattern=r"^(\d{10})?$")
    email: Optional[str] = Field(default=None, max_length=120)
    stage: Optional[Literal["prospecto", "contactado", "cliente", "inactivo"]] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class InteractionIn(BaseModel):
    kind: Literal["llamada", "mensaje", "visita", "nota"] = "nota"
    note: str = Field(min_length=1, max_length=500)


@app.get("/api/admin/customers")
def customers(q: str = "", stage: str = "", user: dict = Depends(current_user)):
    sql = ("SELECT c.*,(SELECT COUNT(*) FROM appointments a WHERE a.customer_id=c.id) AS appointments "
           "FROM customers c WHERE (c.alias LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)")
    args = [f"%{q}%"] * 3
    if stage:
        sql += " AND c.stage=?"
        args.append(stage)
    with connect() as db:
        return [dict(r) for r in db.execute(sql + " ORDER BY c.id DESC", args)]


@app.post("/api/admin/customers", status_code=201)
def create_customer(data: CustomerIn, user: dict = Depends(current_user)):
    with connect() as db:
        cid = db.execute("INSERT INTO customers(alias,phone,email,stage,source,notes) VALUES(?,?,?,?,?,?)",
                         (data.alias, data.phone, data.email, data.stage, data.source, data.notes)).lastrowid
        audit(db, user, f"alta de cliente {cid}")
    return {"id": cid}


@app.get("/api/admin/customers/{cid}")
def customer_detail(cid: int, user: dict = Depends(current_user)):
    with connect() as db:
        c = db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Cliente no encontrado")
        inter = db.execute("SELECT kind,note,created_at FROM interactions WHERE customer_id=? ORDER BY id DESC",
                           (cid,)).fetchall()
        appts = db.execute(services.APPT_SELECT + " WHERE a.customer_id=? ORDER BY a.visit_date DESC",
                           (cid,)).fetchall()
        return {**dict(c), "interactions": [dict(r) for r in inter], "appointments": [dict(r) for r in appts]}


@app.patch("/api/admin/customers/{cid}")
def update_customer(cid: int, data: CustomerPatch, user: dict = Depends(current_user)):
    fields = data.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "Sin cambios")
    with connect() as db:
        sets = ",".join(f"{k}=?" for k in fields)
        if db.execute(f"UPDATE customers SET {sets} WHERE id=?", [*fields.values(), cid]).rowcount == 0:
            raise HTTPException(404, "Cliente no encontrado")
        if "stage" in fields:
            services.log_interaction(db, cid, "nota", f"Etapa cambiada a {fields['stage']} por {user['u']}")
        audit(db, user, f"edición de cliente {cid}")
    return {"ok": True}


@app.post("/api/admin/customers/{cid}/interactions", status_code=201)
def add_interaction(cid: int, data: InteractionIn, user: dict = Depends(current_user)):
    with connect() as db:
        if not db.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Cliente no encontrado")
        services.log_interaction(db, cid, data.kind, data.note)
    return {"ok": True}


@app.get("/api/admin/pipeline")
def pipeline(user: dict = Depends(current_user)):
    with connect() as db:
        rows = db.execute("SELECT stage,COUNT(*) n FROM customers GROUP BY stage").fetchall()
    counts = {r["stage"]: r["n"] for r in rows}
    return {s: counts.get(s, 0) for s in ("prospecto", "contactado", "cliente", "inactivo")}


# ------------------------------------------------------------ Citas y pagos
class StatusIn(BaseModel):
    status: Literal["completada", "cancelada"]


class PaymentIn(BaseModel):
    method: Literal["efectivo", "tarjeta", "transferencia"]


@app.get("/api/admin/appointments")
def admin_appointments(status: str = "", day: str = "", start: str = "", end: str = "", q: str = "",
                       user: dict = Depends(current_user)):
    sql, args = services.APPT_SELECT + " WHERE 1=1", []
    if status:
        sql += " AND a.status=?"
        args.append(status)
    if day:
        sql += " AND a.visit_date=?"
        args.append(day)
    if start and end:
        sql += " AND a.visit_date BETWEEN ? AND ?"
        args += [start, end]
    if q:
        sql += " AND (a.code LIKE ? OR c.alias LIKE ? OR c.phone LIKE ?)"
        args += [f"%{q}%"] * 3
    with connect() as db:
        return [dict(r) for r in db.execute(sql + " ORDER BY a.visit_date DESC,a.visit_time DESC LIMIT 500", args)]


@app.post("/api/admin/appointments", status_code=201)
def admin_create_appointment(data: BookIn, user: dict = Depends(current_user)):
    """Cita capturada en recepción (paciente presencial o por teléfono)."""
    _check_email(data.email)
    with connect() as db:
        appt = services.book_appointment(db, data.specialty_id, data.date, data.time, data.alias.strip(),
                                         data.phone, data.email, channel="recepcion")
        audit(db, user, f"alta de cita {appt['code']} en recepción")
    return appt


EXPORTS = {
    "pacientes": ("SELECT id,alias,phone AS telefono,email AS correo,stage AS etapa,source AS origen,"
                  "created_at AS alta FROM customers ORDER BY id"),
    "citas": ("SELECT a.code AS folio,a.visit_date AS fecha,a.visit_time AS hora,a.status AS estado,"
              "a.channel AS canal,c.alias AS paciente,s.name AS especialidad,p.name AS profesional,s.price AS precio "
              "FROM appointments a JOIN customers c ON c.id=a.customer_id JOIN professionals p "
              "ON p.id=a.professional_id JOIN specialties s ON s.id=p.specialty_id ORDER BY a.visit_date,a.visit_time"),
    "pagos": ("SELECT pay.invoice_folio AS factura,pay.created_at AS fecha,a.code AS cita,c.alias AS paciente,"
              "pay.method AS metodo,pay.amount AS monto FROM payments pay JOIN appointments a "
              "ON a.id=pay.appointment_id JOIN customers c ON c.id=a.customer_id ORDER BY pay.id"),
    "inventario": "SELECT name AS articulo,stock AS existencias,min_stock AS minimo,unit_cost AS costo FROM inventory",
}


@app.get("/api/admin/export/{kind}.csv")
def export_csv(kind: str, user: dict = Depends(current_user)):
    if kind not in EXPORTS:
        raise HTTPException(404, "Exportación no disponible")
    with connect() as db:
        cur = db.execute(EXPORTS[kind])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        audit(db, user, f"exportación CSV de {kind}")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:  # Evita inyección de fórmulas al abrir el CSV en Excel.
        w.writerow(["'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in r])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="medibot-{kind}.csv"'})


@app.post("/api/admin/appointments/{aid}/status")
def set_status(aid: int, data: StatusIn, user: dict = Depends(current_user)):
    with connect() as db:
        row = db.execute("SELECT status,customer_id,code FROM appointments WHERE id=?", (aid,)).fetchone()
        if not row:
            raise HTTPException(404, "Cita no encontrada")
        if row["status"] != "confirmada":
            raise HTTPException(409, f"La cita ya está {row['status']}")
        db.execute("UPDATE appointments SET status=? WHERE id=?", (data.status, aid))
        services.log_interaction(db, row["customer_id"], "visita" if data.status == "completada" else "nota",
                                 f"Cita {row['code']} marcada como {data.status}")
        audit(db, user, f"cita {row['code']} -> {data.status}")
    return {"ok": True}


@app.post("/api/admin/appointments/{aid}/payment", status_code=201)
def register_payment(aid: int, data: PaymentIn, user: dict = Depends(current_user)):
    """Cobro y factura SIMULADOS (sin timbrado fiscal real)."""
    with connect() as db:
        row = db.execute("SELECT a.status,a.code,s.price FROM appointments a JOIN professionals p "
                         "ON p.id=a.professional_id JOIN specialties s ON s.id=p.specialty_id WHERE a.id=?",
                         (aid,)).fetchone()
        if not row:
            raise HTTPException(404, "Cita no encontrada")
        if row["status"] != "completada":
            raise HTTPException(409, "Sólo se cobran citas completadas")
        if db.execute("SELECT 1 FROM payments WHERE appointment_id=?", (aid,)).fetchone():
            raise HTTPException(409, "La cita ya tiene pago registrado")
        folio = services.new_code("FAC-", 6)
        db.execute("INSERT INTO payments(appointment_id,amount,method,invoice_folio) VALUES(?,?,?,?)",
                   (aid, row["price"], data.method, folio))
        audit(db, user, f"pago {folio} de cita {row['code']}")
    return {"invoice": folio, "amount": row["price"], "method": data.method}


@app.get("/api/admin/payments")
def payments(user: dict = Depends(current_user)):
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT pay.invoice_folio AS invoice,pay.amount,pay.method,pay.created_at,a.code,c.alias "
            "FROM payments pay JOIN appointments a ON a.id=pay.appointment_id "
            "JOIN customers c ON c.id=a.customer_id ORDER BY pay.id DESC LIMIT 300")]


# ----------------------------------------------------- ERP: catálogo y horarios
class SpecialtyIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    price: float = Field(ge=0, le=100000)
    description: str = Field(default="", max_length=200)
    active: bool = True


class ProfessionalIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    specialty_id: int
    active: bool = True


class ScheduleIn(BaseModel):
    professional_id: int
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    slot_minutes: int = Field(default=60, ge=15, le=120)


@app.get("/api/admin/catalog")
def catalog(user: dict = Depends(current_user)):
    with connect() as db:
        return {"specialties": [dict(r) for r in db.execute("SELECT * FROM specialties ORDER BY id")],
                "professionals": [dict(r) for r in db.execute(
                    "SELECT p.*,s.name AS specialty FROM professionals p JOIN specialties s "
                    "ON s.id=p.specialty_id ORDER BY p.id")]}


@app.post("/api/admin/specialties", status_code=201)
def add_specialty(data: SpecialtyIn, user: dict = Depends(require_admin)):
    with connect() as db:
        try:
            sid = db.execute("INSERT INTO specialties(name,price,description,active) VALUES(?,?,?,?)",
                             (data.name, data.price, data.description, int(data.active))).lastrowid
        except Exception:
            raise HTTPException(409, "Ya existe una especialidad con ese nombre")
        audit(db, user, f"alta de especialidad {data.name}")
    return {"id": sid}


@app.put("/api/admin/specialties/{sid}")
def edit_specialty(sid: int, data: SpecialtyIn, user: dict = Depends(require_admin)):
    with connect() as db:
        if db.execute("UPDATE specialties SET name=?,price=?,description=?,active=? WHERE id=?",
                      (data.name, data.price, data.description, int(data.active), sid)).rowcount == 0:
            raise HTTPException(404, "Especialidad no encontrada")
        audit(db, user, f"edición de especialidad {sid}")
    return {"ok": True}


@app.post("/api/admin/professionals", status_code=201)
def add_professional(data: ProfessionalIn, user: dict = Depends(require_admin)):
    with connect() as db:
        if not db.execute("SELECT 1 FROM specialties WHERE id=?", (data.specialty_id,)).fetchone():
            raise HTTPException(404, "Especialidad no encontrada")
        pid = db.execute("INSERT INTO professionals(name,specialty_id,active) VALUES(?,?,?)",
                         (data.name, data.specialty_id, int(data.active))).lastrowid
        audit(db, user, f"alta de profesional {data.name}")
    return {"id": pid}


@app.put("/api/admin/professionals/{pid}")
def edit_professional(pid: int, data: ProfessionalIn, user: dict = Depends(require_admin)):
    with connect() as db:
        if db.execute("UPDATE professionals SET name=?,specialty_id=?,active=? WHERE id=?",
                      (data.name, data.specialty_id, int(data.active), pid)).rowcount == 0:
            raise HTTPException(404, "Profesional no encontrado")
        audit(db, user, f"edición de profesional {pid}")
    return {"ok": True}


@app.get("/api/admin/schedules")
def schedules(user: dict = Depends(current_user)):
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT sc.*,p.name AS professional FROM schedules sc JOIN professionals p ON p.id=sc.professional_id "
            "ORDER BY p.id,sc.weekday")]


@app.post("/api/admin/schedules", status_code=201)
def add_schedule(data: ScheduleIn, user: dict = Depends(require_admin)):
    if data.start >= data.end:
        raise HTTPException(400, "La hora de inicio debe ser menor que la de fin")
    with connect() as db:
        if not db.execute("SELECT 1 FROM professionals WHERE id=?", (data.professional_id,)).fetchone():
            raise HTTPException(404, "Profesional no encontrado")
        sid = db.execute("INSERT INTO schedules(professional_id,weekday,start,end,slot_minutes) VALUES(?,?,?,?,?)",
                         (data.professional_id, data.weekday, data.start, data.end, data.slot_minutes)).lastrowid
        audit(db, user, f"alta de horario {sid}")
    return {"id": sid}


@app.delete("/api/admin/schedules/{sid}")
def delete_schedule(sid: int, user: dict = Depends(require_admin)):
    with connect() as db:
        if db.execute("DELETE FROM schedules WHERE id=?", (sid,)).rowcount == 0:
            raise HTTPException(404, "Horario no encontrado")
        audit(db, user, f"baja de horario {sid}")
    return {"ok": True}


# ----------------------------------------------------------- ERP: inventario
class ItemIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    stock: int = Field(default=0, ge=0, le=100000)
    min_stock: int = Field(default=0, ge=0, le=100000)
    unit_cost: float = Field(default=0, ge=0, le=100000)


class MovementIn(BaseModel):
    delta: int = Field(ge=-10000, le=10000)
    reason: str = Field(min_length=2, max_length=80)

    @field_validator("delta")
    @classmethod
    def not_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("El movimiento no puede ser 0")
        return v


@app.get("/api/admin/inventory")
def inventory(user: dict = Depends(current_user)):
    with connect() as db:
        return [{**dict(r), "low": r["stock"] <= r["min_stock"]} for r in
                db.execute("SELECT * FROM inventory ORDER BY name")]


@app.post("/api/admin/inventory", status_code=201)
def add_item(data: ItemIn, user: dict = Depends(require_admin)):
    with connect() as db:
        try:
            iid = db.execute("INSERT INTO inventory(name,stock,min_stock,unit_cost) VALUES(?,?,?,?)",
                             (data.name, data.stock, data.min_stock, data.unit_cost)).lastrowid
        except Exception:
            raise HTTPException(409, "Ya existe un artículo con ese nombre")
        audit(db, user, f"alta de artículo {data.name}")
    return {"id": iid}


@app.post("/api/admin/inventory/{iid}/movement")
def movement(iid: int, data: MovementIn, user: dict = Depends(current_user)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT stock FROM inventory WHERE id=?", (iid,)).fetchone()
        if not row:
            db.execute("ROLLBACK")
            raise HTTPException(404, "Artículo no encontrado")
        if row["stock"] + data.delta < 0:
            db.execute("ROLLBACK")
            raise HTTPException(409, "No hay existencias suficientes")
        db.execute("UPDATE inventory SET stock=stock+? WHERE id=?", (data.delta, iid))
        db.execute("INSERT INTO inventory_movements(item_id,delta,reason) VALUES(?,?,?)",
                   (iid, data.delta, data.reason))
        db.execute("COMMIT")
        audit(db, user, f"movimiento {data.delta:+d} en artículo {iid}")
    return {"ok": True}


@app.get("/api/admin/inventory/{iid}/movements")
def movements(iid: int, user: dict = Depends(current_user)):
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT delta,reason,created_at FROM inventory_movements WHERE item_id=? ORDER BY id DESC LIMIT 50",
            (iid,))]


# ----------------------------------------------------- Dashboard y reportes
@app.get("/api/admin/dashboard")
def dashboard(user: dict = Depends(current_user)):
    today = date.today().isoformat()
    with connect() as db:
        one = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731
        return {
            "today": one("SELECT COUNT(*) FROM appointments WHERE visit_date=? AND status='confirmada'", today),
            "pending": one("SELECT COUNT(*) FROM appointments WHERE status='confirmada' AND visit_date>=?", today),
            "completed": one("SELECT COUNT(*) FROM appointments WHERE status='completada'"),
            "requests": one("SELECT COUNT(*) FROM contact_requests WHERE status='pendiente'"),
            "customers": one("SELECT COUNT(*) FROM customers"),
            "prospects": one("SELECT COUNT(*) FROM customers WHERE stage='prospecto'"),
            "income": one("SELECT COALESCE(SUM(amount),0) FROM payments"),
            "low_stock": one("SELECT COUNT(*) FROM inventory WHERE stock<=min_stock"),
            "chats": one("SELECT COUNT(*) FROM chat_logs"),
        }


@app.get("/api/admin/reports")
def reports(user: dict = Depends(current_user)):
    with connect() as db:
        q = lambda sql: [dict(r) for r in db.execute(sql)]  # noqa: E731
        return {
            "income_by_specialty": q(
                "SELECT s.name AS label,SUM(pay.amount) AS value FROM payments pay JOIN appointments a "
                "ON a.id=pay.appointment_id JOIN professionals p ON p.id=a.professional_id "
                "JOIN specialties s ON s.id=p.specialty_id GROUP BY s.id ORDER BY value DESC"),
            "income_by_month": q("SELECT substr(created_at,1,7) AS label,SUM(amount) AS value FROM payments "
                                 "GROUP BY label ORDER BY label"),
            "appointments_by_status": q("SELECT status AS label,COUNT(*) AS value FROM appointments GROUP BY status"),
            "appointments_by_specialty": q(
                "SELECT s.name AS label,COUNT(*) AS value FROM appointments a JOIN professionals p "
                "ON p.id=a.professional_id JOIN specialties s ON s.id=p.specialty_id GROUP BY s.id ORDER BY value DESC"),
            "chat_intents": q("SELECT intent AS label,COUNT(*) AS value FROM chat_logs GROUP BY intent "
                              "ORDER BY value DESC"),
            "channels": q("SELECT channel AS label,COUNT(*) AS value FROM appointments GROUP BY channel"),
            "low_stock": q("SELECT name AS label,stock AS value FROM inventory WHERE stock<=min_stock"),
            "income_by_day": q("SELECT substr(created_at,1,10) AS label,SUM(amount) AS value FROM payments "
                               "WHERE created_at>=date('now','localtime','-29 days') GROUP BY label ORDER BY label"),
            "appointments_by_day": q("SELECT visit_date AS label,COUNT(*) AS value FROM appointments "
                                     "WHERE status!='cancelada' AND visit_date BETWEEN date('now','localtime','-14 days') "
                                     "AND date('now','localtime','+14 days') GROUP BY label ORDER BY label"),
            "methods": q("SELECT method AS label,SUM(amount) AS value FROM payments GROUP BY method"),
        }


# ------------------------------------------- Bandeja de atención humana (CRM)
class RequestStatusIn(BaseModel):
    status: Literal["pendiente", "atendida", "descartada"]
    note: str = Field(default="", max_length=300)


@app.get("/api/admin/requests")
def contact_requests(status: str = "", user: dict = Depends(current_user)):
    sql, args = ("SELECT r.*,c.stage FROM contact_requests r LEFT JOIN customers c ON c.id=r.customer_id "
                 "WHERE 1=1"), []
    if status:
        sql += " AND r.status=?"
        args.append(status)
    with connect() as db:
        return [{**dict(r), "topic_label": CONTACT_TOPICS.get(r["topic"], r["topic"])}
                for r in db.execute(sql + " ORDER BY r.status='pendiente' DESC, r.id DESC LIMIT 300", args)]


@app.post("/api/admin/requests/{rid}/status")
def set_request_status(rid: int, data: RequestStatusIn, user: dict = Depends(current_user)):
    with connect() as db:
        row = db.execute("SELECT customer_id FROM contact_requests WHERE id=?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, "Solicitud no encontrada")
        done = data.status != "pendiente"
        db.execute("UPDATE contact_requests SET status=?,handled_by=?,handled_at=? WHERE id=?",
                   (data.status, user["u"] if done else "",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S") if done else "", rid))
        if row["customer_id"]:
            note = f"Solicitud de contacto marcada como {data.status} por {user['u']}"
            services.log_interaction(db, row["customer_id"], "llamada" if data.status == "atendida" else "nota",
                                     note + (f": {data.note}" if data.note else ""))
            if data.status == "atendida":
                db.execute("UPDATE customers SET stage='contactado' WHERE id=? AND stage='prospecto'",
                           (row["customer_id"],))
        audit(db, user, f"solicitud {rid} -> {data.status}")
    return {"ok": True}


# ------------------------------------------------ Búsqueda global y actividad
@app.get("/api/admin/search")
def global_search(q: str = "", user: dict = Depends(current_user)):
    q = q.strip()[:60]
    if len(q) < 2:
        return {"customers": [], "appointments": [], "invoices": []}
    like = f"%{q}%"
    with connect() as db:
        return {
            "customers": [dict(r) for r in db.execute(
                "SELECT id,alias,phone,stage FROM customers WHERE alias LIKE ? OR phone LIKE ? OR email LIKE ? "
                "ORDER BY id DESC LIMIT 6", (like, like, like))],
            "appointments": [dict(r) for r in db.execute(
                services.APPT_SELECT + " WHERE a.code LIKE ? OR c.alias LIKE ? OR c.phone LIKE ? "
                "ORDER BY a.visit_date DESC LIMIT 6", (like, like, like))],
            "invoices": [dict(r) for r in db.execute(
                "SELECT pay.invoice_folio AS invoice,pay.amount,a.code FROM payments pay JOIN appointments a "
                "ON a.id=pay.appointment_id WHERE pay.invoice_folio LIKE ? LIMIT 4", (like,))],
        }


@app.get("/api/admin/activity")
def activity(user: dict = Depends(current_user)):
    """Actividad reciente combinada para el dashboard."""
    with connect() as db:
        rows = db.execute("""
          SELECT 'cita' AS kind, a.created_at AS at, c.alias AS who,
                 s.name || ' · ' || a.visit_date || ' ' || a.visit_time AS what, a.channel AS extra
            FROM appointments a JOIN customers c ON c.id=a.customer_id
            JOIN professionals p ON p.id=a.professional_id JOIN specialties s ON s.id=p.specialty_id
          UNION ALL
          SELECT 'pago', pay.created_at, c.alias, pay.invoice_folio || ' · $' || CAST(pay.amount AS INT), pay.method
            FROM payments pay JOIN appointments a ON a.id=pay.appointment_id JOIN customers c ON c.id=a.customer_id
          UNION ALL
          SELECT 'solicitud', r.created_at, r.alias, r.topic, r.status FROM contact_requests r
          ORDER BY at DESC LIMIT 12""").fetchall()
        return [{**dict(r), "what": CONTACT_TOPICS.get(r["what"], r["what"]) if r["kind"] == "solicitud" else r["what"]}
                for r in rows]


# ------------------------------------------------ Métricas del asistente
FUNNEL = ["spec", "date", "time", "alias", "phone", "confirm", "done"]
FUNNEL_LABELS = {"spec": "Especialidad", "date": "Fecha", "time": "Horario", "alias": "Datos", "phone": "Teléfono",
                 "confirm": "Resumen", "done": "Reservada"}


@app.get("/api/admin/chat-metrics")
def chat_metrics(days: int = 30, user: dict = Depends(current_user)):
    days = max(1, min(days, 365))
    since = f"-{days} days"
    with connect() as db:
        def distinct(event, detail=None):
            sql = ("SELECT COUNT(DISTINCT session) FROM chat_events WHERE event=? "
                   "AND created_at>=datetime('now','localtime',?)")
            args = [event, since]
            if detail is not None:
                sql += " AND detail=?"
                args.append(detail)
            return db.execute(sql, args).fetchone()[0]

        def count(event):
            return db.execute("SELECT COUNT(*) FROM chat_events WHERE event=? AND created_at>=datetime('now',"
                              "'localtime',?)", (event, since)).fetchone()[0]

        conversations = distinct("message")
        funnel = [{"step": s, "label": FUNNEL_LABELS[s], "sessions": distinct("step", s)} for s in FUNNEL]
        started = funnel[0]["sessions"] or max((f["sessions"] for f in funnel), default=0)
        booked = distinct("booking_completed")
        drop = []
        for i, f in enumerate(funnel[:-1]):
            nxt = funnel[i + 1]["sessions"]
            drop.append({"label": f["label"], "value": max(0, f["sessions"] - nxt)})
        top_fallback = [dict(r) for r in db.execute(
            "SELECT detail AS label,COUNT(*) AS value FROM chat_events WHERE event='fallback' AND detail!='' "
            "AND created_at>=datetime('now','localtime',?) GROUP BY detail ORDER BY value DESC LIMIT 10", (since,))]
        intents = [dict(r) for r in db.execute(
            "SELECT detail AS label,COUNT(*) AS value FROM chat_events WHERE event='message' "
            "AND created_at>=datetime('now','localtime',?) GROUP BY detail ORDER BY value DESC", (since,))]
        messages = sum(i["value"] for i in intents)
        not_understood = next((i["value"] for i in intents if i["label"] == "otro"), 0) + count("fallback")
        return {
            "days": days, "conversations": conversations, "messages": messages,
            "booking_started": started, "bookings": booked,
            "conversion": round(booked / started * 100, 1) if started else 0,
            "fallbacks": not_understood, "understood": round((1 - not_understood / messages) * 100, 1) if messages else 0,
            "human_requests": count("human_request"), "lookups": count("lookup_completed"),
            "cancellations": count("cancel_completed"), "availability_errors": count("availability_error"),
            "access_failed": count("access_failed"), "funnel": funnel, "abandon": drop,
            "top_fallback": top_fallback, "intents": intents,
        }


@app.get("/api/admin/audit")
def audit_log(user: dict = Depends(require_admin)):
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT username,action,created_at FROM audit_log "
                                            "ORDER BY id DESC LIMIT 200")]
