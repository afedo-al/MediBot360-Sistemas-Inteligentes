"""Reglas de negocio compartidas por la API, el chatbot, el CRM y el ERP."""
import secrets
import sqlite3
import time as _time
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from .security import hash_password, verify_password

MAX_DAYS_AHEAD = 45
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PIN_DIGITS = 6
# Mensaje único para folio inexistente, PIN incorrecto o cita sin PIN: no revela si la reservación existe.
ACCESS_DENIED = "No encontramos una cita con ese folio y PIN"
MAX_ATTEMPTS, ATTEMPT_WINDOW = 5, 15 * 60
_attempts: dict[str, list[float]] = {}
_DUMMY_HASH = hash_password("no-pin")


def new_code(prefix: str = "MB-", size: int = 8) -> str:
    return prefix + "".join(secrets.choice(CODE_ALPHABET) for _ in range(size))


def new_pin() -> str:
    return f"{secrets.randbelow(10 ** PIN_DIGITS):0{PIN_DIGITS}d}"


def check_date(value: str) -> date:
    try:
        day = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(400, "Formato de fecha inválido (AAAA-MM-DD)")
    if day < date.today() or day > date.today() + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(400, "Fecha fuera de rango")
    if day.weekday() == 6:
        raise HTTPException(400, "No hay citas los domingos")
    return day


def _times(start: str, end: str, step: int):
    cur = datetime.strptime(start, "%H:%M")
    stop = datetime.strptime(end, "%H:%M")
    while cur < stop:
        yield cur.strftime("%H:%M")
        cur += timedelta(minutes=step)


def slots_by_professional(db: sqlite3.Connection, specialty_id: int, day: date,
                          professional_id: int | None = None) -> list[dict]:
    """Todas las combinaciones libres (hora, especialista) de una especialidad en una fecha.

    Respeta horarios configurados, citas ocupadas, especialistas inactivos y horas ya pasadas.
    """
    sql = "SELECT id,name FROM professionals WHERE specialty_id=? AND active=1"
    args: list = [specialty_id]
    if professional_id is not None:
        sql += " AND id=?"
        args.append(professional_id)
    now = datetime.now()
    out = []
    for p in db.execute(sql + " ORDER BY id", args).fetchall():
        busy = {r[0] for r in db.execute(
            "SELECT visit_time FROM appointments WHERE professional_id=? AND visit_date=? AND status!='cancelada'",
            (p["id"], day.isoformat()))}
        for s in db.execute("SELECT start,end,slot_minutes FROM schedules WHERE professional_id=? AND weekday=?",
                            (p["id"], day.weekday())):
            for t in _times(s["start"], s["end"], s["slot_minutes"]):
                if t in busy or (day == now.date() and t <= now.strftime("%H:%M")):
                    continue
                out.append({"time": t, "professional_id": p["id"], "professional": p["name"]})
    return sorted(out, key=lambda s: (s["time"], s["professional_id"]))


def available_slots(db: sqlite3.Connection, specialty_id: int, day: date) -> list[dict]:
    """Horarios libres de una especialidad (una opción por hora: el primer especialista libre)."""
    seen: dict[str, dict] = {}
    for s in slots_by_professional(db, specialty_id, day):
        seen.setdefault(s["time"], s)
    return list(seen.values())


def next_available(db: sqlite3.Connection, specialty_id: int, max_days: int = MAX_DAYS_AHEAD,
                   professional_id: int | None = None, after: date | None = None) -> dict | None:
    """Primer horario libre de una especialidad (opcionalmente de un especialista y posterior a una fecha)."""
    day = after + timedelta(days=1) if after else date.today()
    limit = date.today() + timedelta(days=min(max_days, MAX_DAYS_AHEAD))
    while day <= limit:
        if day.weekday() != 6:
            slots = slots_by_professional(db, specialty_id, day, professional_id)
            if slots:
                return {"date": day.isoformat(), **slots[0]}
        day += timedelta(days=1)
    return None


def find_or_create_customer(db, alias: str, phone: str = "", email: str = "", source: str = "web") -> int:
    if phone:
        row = db.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
    else:
        row = db.execute("SELECT id FROM customers WHERE lower(alias)=lower(?) AND phone=''", (alias,)).fetchone()
    if row:
        cid = row["id"]
        if email:
            db.execute("UPDATE customers SET email=? WHERE id=? AND email=''", (email, cid))
        return cid
    return db.execute("INSERT INTO customers(alias,phone,email,source) VALUES(?,?,?,?)",
                      (alias, phone, email, source)).lastrowid


def log_interaction(db, customer_id: int, kind: str, note: str) -> None:
    db.execute("INSERT INTO interactions(customer_id,kind,note) VALUES(?,?,?)", (customer_id, kind, note))


def book_appointment(db, specialty_id: int, day_str: str, time: str, alias: str, phone: str = "",
                     email: str = "", channel: str = "web", professional_id: int | None = None) -> dict:
    """Valida en el servidor y registra de forma atómica.

    Devuelve el folio y un PIN privado de 6 dígitos que solo se muestra una vez (se guarda con hash).
    """
    day = check_date(day_str)
    spec = db.execute("SELECT id,name,price FROM specialties WHERE id=? AND active=1", (specialty_id,)).fetchone()
    if not spec:
        raise HTTPException(404, "Especialidad no encontrada")
    pin = new_pin()
    pin_hash = hash_password(pin)  # Fuera de la transacción: el hash es costoso y no debe bloquear la base.
    db.execute("BEGIN IMMEDIATE")
    try:
        free = [s for s in slots_by_professional(db, specialty_id, day, professional_id) if s["time"] == time]
        if not free:
            db.execute("ROLLBACK")
            raise HTTPException(409, "Horario ocupado o no disponible")
        slot = free[0]
        cid = find_or_create_customer(db, alias, phone, email, source=channel)
        code = new_code()
        db.execute("INSERT INTO appointments(code,customer_id,professional_id,visit_date,visit_time,channel,pin_hash) "
                   "VALUES(?,?,?,?,?,?,?)",
                   (code, cid, slot["professional_id"], day.isoformat(), time, channel, pin_hash))
        db.execute("UPDATE customers SET stage='cliente' WHERE id=? AND stage IN ('prospecto','contactado')", (cid,))
        log_interaction(db, cid, "cita", f"Cita {code}: {spec['name']} con {slot['professional']} el "
                                         f"{day.isoformat()} a las {time} ({channel})")
        db.execute("COMMIT")
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
        raise HTTPException(409, "Horario ocupado")
    except HTTPException:
        raise
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    return {"code": code, "pin": pin, "specialty": spec["name"], "professional": slot["professional"],
            "professional_id": slot["professional_id"], "date": day.isoformat(), "time": time,
            "price": spec["price"], "status": "confirmada"}


APPT_SELECT = """SELECT a.id,a.code,a.visit_date AS date,a.visit_time AS time,a.status,a.channel,a.created_at,
  c.id AS customer_id,c.alias,c.phone,p.name AS professional,s.name AS specialty,s.price,
  (SELECT invoice_folio FROM payments WHERE appointment_id=a.id) AS invoice
  FROM appointments a JOIN customers c ON c.id=a.customer_id
  JOIN professionals p ON p.id=a.professional_id JOIN specialties s ON s.id=p.specialty_id"""


def _throttle_key(code: str, client: str) -> list[str]:
    return [f"code:{code}", f"client:{client}"] if client else [f"code:{code}"]


def _check_throttle(keys: list[str]) -> None:
    now = _time.time()
    for k in keys:
        recent = [t for t in _attempts.get(k, []) if now - t < ATTEMPT_WINDOW]
        _attempts[k] = recent
        if len(recent) >= MAX_ATTEMPTS:
            raise HTTPException(429, "Demasiados intentos. Espera 15 minutos o acude a recepción.")


def verify_access(db, code: str, pin: str, client: str = "") -> dict:
    """Valida folio + PIN con límite de intentos por folio y por cliente. Devuelve la cita pública."""
    code = str(code or "").upper().strip()[:16]
    pin = str(pin or "").strip()
    keys = _throttle_key(code, client)
    _check_throttle(keys)
    row = db.execute(APPT_SELECT.replace("SELECT a.id", "SELECT a.pin_hash,a.id") + " WHERE a.code=?",
                     (code,)).fetchone()
    # Se calcula el hash aunque el folio no exista para que el tiempo de respuesta no lo delate.
    stored = row["pin_hash"] if row and row["pin_hash"] else _DUMMY_HASH
    ok = bool(verify_password(pin, stored) and row and row["pin_hash"] and pin.isdigit())
    if not ok:
        for k in keys:
            _attempts.setdefault(k, []).append(_time.time())
        raise HTTPException(404, ACCESS_DENIED)
    for k in keys:
        _attempts.pop(k, None)
    d = dict(row)
    for k in ("pin_hash", "phone", "customer_id", "id", "invoice", "alias"):
        d.pop(k, None)
    return d


def get_appointment_public(db, code: str, pin: str, client: str = ""):
    return verify_access(db, code, pin, client)


def cancel_by_code(db, code: str) -> dict:
    """Cancela una cita YA verificada (el llamador debe haber validado folio + PIN)."""
    code = code.upper().strip()
    row = db.execute("SELECT id,status,customer_id FROM appointments WHERE code=?", (code,)).fetchone()
    if not row:
        raise HTTPException(404, ACCESS_DENIED)
    if row["status"] != "confirmada":
        raise HTTPException(409, f"La cita ya está {row['status']} y no puede cancelarse")
    db.execute("UPDATE appointments SET status='cancelada' WHERE id=? AND status='confirmada'", (row["id"],))
    log_interaction(db, row["customer_id"], "nota", f"Cita {code} cancelada por el paciente")
    return {"code": code, "status": "cancelada"}


def cancel_appointment(db, code: str, pin: str, client: str = "") -> dict:
    verify_access(db, code, pin, client)
    return cancel_by_code(db, code)


def create_contact_request(db, alias: str, phone: str, topic: str, source: str = "chatbot") -> int:
    cid = find_or_create_customer(db, alias, phone, source=source)
    rid = db.execute("INSERT INTO contact_requests(customer_id,alias,phone,topic) VALUES(?,?,?,?)",
                     (cid, alias, phone, topic)).lastrowid
    log_interaction(db, cid, "chatbot", f"Solicitó contacto con recepción ({topic})")
    return rid


def clinic_hours(db) -> list[tuple[str, str]]:
    """Horario general de atención calculado a partir de los horarios de los especialistas activos."""
    names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    rows = {r["weekday"]: (r["s"], r["e"]) for r in db.execute(
        "SELECT sc.weekday,MIN(sc.start) s,MAX(sc.end) e FROM schedules sc JOIN professionals p "
        "ON p.id=sc.professional_id WHERE p.active=1 GROUP BY sc.weekday")}
    return [(names[d], f"{rows[d][0]} – {rows[d][1]}" if d in rows else "Cerrado") for d in range(7)]
