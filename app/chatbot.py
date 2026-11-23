"""Recepción virtual MediBot 3.0 — motor conversacional basado en reglas (sin IA generativa).

Arquitectura:
  1. Normalización del texto (minúsculas, sin acentos).
  2. Extracción de entidades: especialidad, especialista o preferencia (doctora/doctor), fecha, hora exacta,
     rango horario («después de las 11», «por la mañana»), folio y acciones («lo antes posible», «otra opción»).
  3. Detección de intención por reglas priorizadas (emergencias y salud primero).
  4. Máquina de estados por flujo: reserva, consulta, cancelación verificada y solicitud de atención humana.
     El estado viaja en el navegador, pero el servidor lo vuelve a validar contra SQLite en cada mensaje
     y recalcula el paso pendiente; nunca confía en el paso declarado por el cliente.
  5. Respuesta con texto breve + componentes (tarjetas, fechas, horarios, resumen, confirmación) y eventos
     anónimos para métricas operativas.

El asistente no diagnostica, no receta y deriva emergencias al 911. Todos los precios, especialistas,
horarios y políticas salen de la base de datos o de app/config.py.
"""
import re
import unicodedata
from datetime import date, timedelta

from fastapi import HTTPException

from . import services
from .config import CLINIC, CONTACT_TOPICS
from .security import check_value, sign_value

# ------------------------------------------------------------------ vocabulario
EMERGENCY = ("emergencia", "urgencia", "urgente", "infarto", "no puedo respirar", "dolor de pecho", "sangrado",
             "desmayo", "accidente", "me muero", "suicid", "quitarme la vida", "envenen", "convulsion", "sobredosis")
# Síntomas de alarma descritos con distintas palabras («me duele mucho el pecho», «me falta el aire»).
EMERGENCY_RE = re.compile(
    r"(duele|dolor|presion|opresion|oprime|punzada)\w*\W+(?:\w+\W+){0,4}?(pecho|corazon)"
    r"|(pecho|corazon)\W+(?:\w+\W+){0,3}?(duele|dolor|oprime)"
    r"|falta(?:\s+de)?\s+(el\s+)?(aire|respiracion)|me\s+ahogo|no\s+puedo\s+respirar|dificultad\s+para\s+respirar"
    r"|perdi\w*\s+(el\s+)?(conocimiento|la\s+conciencia)|me\s+desmay|sangr\w+\s+(mucho|abundante)")


def is_emergency(msg: str) -> bool:
    """Palabras clave o síntomas de alarma: se prioriza el aviso al 911 en cualquier punto de la conversación."""
    return any(k in msg for k in EMERGENCY) or bool(EMERGENCY_RE.search(msg))


HEALTH = ("me duele", "dolor", "fiebre", "diagnostico", "diagnostica", "sintoma", "medicina para", "que medicamento",
          "receta", "tengo una enfermedad", "que tomo", "que me tomo", "es grave", "tratamiento para")
WANT = ("quiero", "necesito", "busco", "me gustaria", "quisiera", "ocupo", "dame", "agendame", "reservame")
YES = ("si", "sí", "confirmar", "confirmo", "ok", "de acuerdo", "correcto", "esta bien", "adelante", "#confirm")
BACK = ("#back", "atras", "regresar", "volver", "paso anterior", "anterior")
EXIT = ("#salir", "salir", "cancelar proceso", "terminar", "olvidalo", "ya no")
DOW = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
NUM_WORDS = {"una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
             "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16}
HOUR = r"(\d{1,2}|" + "|".join(NUM_WORDS) + r")(?::(\d{2}))?"
SPEC_KEYS = {"gener": ("medico general", "consulta general", "medicina general", "chequeo", "revision general"),
             "cardi": ("cardio", "corazon"), "derma": ("derma", "piel", "acne", "manchas", "lunar"),
             "pedia": ("pediat", "nino", "nina", "bebe", "mi hijo", "mi hija"),
             "nutri": ("nutri", "dieta", "bajar de peso", "alimenta"),
             "psico": ("psico", "ansiedad", "estres", "terapia", "emocional")}
TITLES = {"dr", "dra", "psic", "lic", "l", "n", "ln"}

STAGES = ["Servicio", "Fecha", "Horario", "Tus datos", "Confirmar"]
STAGE_OF = {"spec": 1, "pro": 1, "date": 2, "time": 3, "alias": 4, "phone": 4, "confirm": 5}

MAIN_MENU = [{"label": "Agendar cita", "value": "agendar"}, {"label": "Disponibilidad", "value": "disponibilidad"},
             {"label": "Precios", "value": "precios"}, {"label": "Consultar mi cita", "value": "consultar"},
             {"label": "Cancelar cita", "value": "cancelar"}, {"label": "Hablar con recepción", "value": "humano"}]
EXIT_BTN = {"label": "Cancelar proceso", "value": "#salir"}
BACK_BTN = {"label": "← Regresar", "value": "#back"}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text).lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.replace("¿", " ").replace("?", " ").replace("¡", " ").replace("!", " ").split())


def R(text, *, buttons=None, state=None, ui=None, step=None, intent="otro", events=(), action=None, expects=None):
    """Respuesta estándar del asistente."""
    progress = {"current": STAGE_OF[step], "total": len(STAGES), "labels": STAGES} if step in STAGE_OF else None
    return {"reply": text, "buttons": MAIN_MENU if buttons is None else buttons, "state": state or {}, "ui": ui,
            "progress": progress, "intent": intent, "events": list(events), "action": action, "expects": expects}


def fmt_day(d: date) -> str:
    return f"{DOW[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def rel_day(d: date) -> str:
    diff = (d - date.today()).days
    return "hoy" if diff == 0 else "mañana" if diff == 1 else fmt_day(d)


def money(v) -> str:
    return f"${float(v):,.0f} MXN"


def sanitize(msg: str) -> str:
    """Versión anónima de un mensaje no comprendido para mejorar el vocabulario (sin números ni correos)."""
    msg = re.sub(r"\S+@\S+", "[correo]", msg)
    return re.sub(r"\d", "#", msg)[:80]


# ------------------------------------------------------------------ entidades
def find_specialty(db, msg: str):
    """Detecta una especialidad en texto libre (p. ej. «cita con el cardiólogo»)."""
    for s in db.execute("SELECT id,name,price,description FROM specialties WHERE active=1 ORDER BY id").fetchall():
        name = norm(s["name"])
        stem = name.split()[-1][:5]
        if name in msg or any(k in msg for k in SPEC_KEYS.get(stem, ())) or (stem != "gener" and stem in msg):
            return s
    return None


def _pros(db, spec_id=None):
    sql, args = "SELECT id,name,specialty_id FROM professionals WHERE active=1", []
    if spec_id:
        sql += " AND specialty_id=?"
        args.append(spec_id)
    return db.execute(sql + " ORDER BY id", args).fetchall()


def find_professional(db, msg: str, spec_id=None):
    words = set(msg.split())
    for p in _pros(db, spec_id):
        tokens = [t for t in norm(p["name"]).replace(".", " ").split() if t not in TITLES and len(t) >= 4]
        if any(t in words for t in tokens):
            return p
    return None


def gender_pref(msg: str):
    if re.search(r"\b(doctora|la dra|una mujer|mujer|especialista mujer)\b", msg):
        return "f"
    if re.search(r"\b(doctor|el dr|un hombre|hombre)\b", msg):
        return "m"
    return None


def _hour(token: str, minutes: str | None) -> str | None:
    h = NUM_WORDS.get(token) if not token.isdigit() else int(token)
    if h is None or h > 23:
        return None
    if 1 <= h <= 7:  # «a las 4» en horario de clínica significa 16:00
        h += 12
    return f"{h:02d}:{minutes or '00'}"


def parse_range(msg: str):
    """Rangos horarios. Devuelve (rango, texto_restante)."""
    m = re.search(rf"\b(despues de|a partir de|desde|antes de)\s+(?:las?\s+)?{HOUR}\b", msg)
    if m:
        t = _hour(m.group(2), m.group(3))
        if t:
            kind = m.group(1)
            rng = {"max": t, "label": f"antes de las {t}"} if kind == "antes de" else \
                {"min": t, "strict": kind == "despues de", "label": f"{'después de' if kind == 'despues de' else 'desde'} las {t}"}
            return rng, msg[:m.start()] + " " + msg[m.end():]
    if re.search(r"\b(por|en) la manana\b|\btemprano\b|\bmatutino\b", msg):
        return {"max": "12:00", "label": "por la mañana"}, re.sub(r"\b(por|en) la manana\b", " ", msg)
    if re.search(r"\b(por|en) la tarde\b|\bvespertino\b", msg):
        return {"min": "12:00", "strict": False, "label": "por la tarde"}, msg
    return None, msg


def parse_time(msg: str, bare_ok: bool = False):
    m = re.search(rf"\ba las?\s+{HOUR}\b", msg) or re.search(r"\b(\d{1,2}):(\d{2})\b", msg)
    if m:
        return _hour(m.group(1), m.group(2))
    if bare_ok:
        m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(h|hrs|horas)?", msg.strip())
        if m:
            return _hour(m.group(1), m.group(2))
    return None


def in_range(t: str, rng: dict | None) -> bool:
    if not rng:
        return True
    if "min" in rng and (t <= rng["min"] if rng.get("strict") else t < rng["min"]):
        return False
    return not ("max" in rng and t >= rng["max"])


def parse_day(msg: str, today: date | None = None):
    """Fechas en lenguaje natural. Distingue «mañana» (fecha) de «por la mañana» (periodo)."""
    today = today or date.today()
    clean = re.sub(r"\b(en|por|de|a) la manana\b", " ", msg)
    if "pasado manana" in clean:
        return today + timedelta(days=2)
    if re.search(r"\bmanana\b", clean):
        return today + timedelta(days=1)
    if re.search(r"\bhoy\b", clean):
        return today
    if re.search(r"\b(proxima|siguiente) semana\b", clean):
        return today + timedelta(days=7 - today.weekday())
    if "fin de semana" in clean:
        return today + timedelta(days=(5 - today.weekday()) % 7)
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", clean)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        year = year + 2000 if year < 100 else year
        try:
            cand = date(year, mo, d)
            if cand < today and not m.group(3):
                cand = date(year + 1, mo, d)
            return cand
        except ValueError:
            return None
    m = re.search(r"\bel (\d{1,2})\b(?!\s*(:|de la|hrs|h\b))", clean)
    if m and not re.search(r"\b(a las|las) " + m.group(1) + r"\b", clean):
        d = int(m.group(1))
        for add in (0, 1):
            month, year = (today.month + add - 1) % 12 + 1, today.year + (today.month + add - 1) // 12
            try:
                cand = date(year, month, d)
                if cand >= today:
                    return cand
            except ValueError:
                continue
    for name, wd in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", clean):
            delta = (wd - today.weekday()) % 7
            return today + timedelta(days=delta or 7)
    return None


def parse_folio(msg: str):
    m = re.search(r"\bmb-?([a-z0-9]{8})\b", msg)
    return f"MB-{m.group(1).upper()}" if m else None


def extract(db, msg: str, spec_id=None, bare_time=False) -> dict:
    rng, rest = parse_range(msg)
    ent = {"spec": find_specialty(db, msg), "range": rng, "day": parse_day(msg),
           "time": parse_time(rest, bare_time), "gender": gender_pref(msg), "folio": parse_folio(msg),
           "asap": bool(re.search(r"lo antes posible|lo mas pronto|cuanto antes|primer horario|lo mas proximo|"
                                  r"primera cita|lo mas rapido", msg)),
           "week": bool(re.search(r"\besta semana\b", msg)),
           "other_day": bool(re.search(r"otro dia|otra fecha|no puedo ese|ese dia no|otra opcion|no me queda|"
                                       r"otro dia|dia siguiente|mas adelante", msg)),
           "other_time": bool(re.search(r"otro horario|otra hora", msg))}
    ent["pro"] = find_professional(db, msg, (ent["spec"]["id"] if ent["spec"] else spec_id))
    return ent


def has_booking_entity(ent: dict) -> bool:
    return any(ent[k] for k in ("spec", "pro", "day", "time", "range", "asap", "other_day", "other_time", "gender"))


def detect_intent(msg: str) -> str:
    if is_emergency(msg):
        return "emergencia"
    if any(k in msg for k in HEALTH):
        return "salud"
    rules = [("humano", ("humano", "recepcion", "una persona", "asesor", "operador", "llamenme", "que me llamen",
                         "telefono de", "contacto")),
             ("cancelar", ("cancel", "anular")),
             ("consultar", ("consultar", "consulta mi", "ver mi cita", "mi cita", "folio", "estado de", "ya tengo",
                            "mi reserv")),
             ("pagos", ("pago", "pagar", "tarjeta", "efectivo", "transferencia", "factura", "seguro", "aseguradora")),
             ("ubicacion", ("donde", "ubicacion", "direccion", "como llego", "estacionamiento", "mapa")),
             ("preparacion", ("que llevo", "que debo llevar", "llegar antes", "requisitos", "preparar")),
             ("disponibilidad", ("disponib", "que tienen", "tienen algo", "hay lugar", "hay espacio", "cuando hay",
                                 "esta semana", "lo antes posible", "lo mas pronto", "cuanto antes", "proximo")),
             ("agendar", ("agend", "reserv", "cita", "turno", "apart", "consulta con")),
             ("precios", ("precio", "costo", "cuesta", "cuanto sale", "tarifa", "cobran", "economic", "barat",
                          "mas cara", "mas caro")),
             ("horarios", ("horario", "abren", "cierran", "atienden", "a que hora")),
             ("especialidades", ("especialidad", "servicio", "doctor", "medico", "especialista")),
             ("despedida", ("gracias", "adios", "hasta luego", "bye", "es todo")),
             ("saludo", ("hola", "buen", "hey", "saludos", "ayuda", "menu", "inicio", "que puedes"))]
    for name, keys in rules:
        if any(re.search(rf"\b{re.escape(k)}", msg) for k in keys):
            return name
    return "otro"


# ------------------------------------------------------------------ validación del estado
def _clean_state(db, st: dict) -> tuple[dict, list[str]]:
    """Revalida en el servidor todo lo que llega del navegador."""
    notes: list[str] = []
    flow = st.get("flow")
    if flow not in ("book", "consult", "cancel", "lead"):
        return {}, notes
    out: dict = {"flow": flow}
    if flow == "book":
        spec = None
        if isinstance(st.get("spec_id"), int):
            spec = db.execute("SELECT id FROM specialties WHERE id=? AND active=1", (st["spec_id"],)).fetchone()
        if spec:
            out["spec_id"] = spec["id"]
            if isinstance(st.get("pro_id"), int) and any(p["id"] == st["pro_id"] for p in _pros(db, spec["id"])):
                out["pro_id"] = st["pro_id"]
        if st.get("gender") in ("f", "m"):
            out["gender"] = st["gender"]
        for flag in ("want_pro", "asap"):
            if st.get(flag) is True:
                out[flag] = True
        rng = st.get("range")
        if isinstance(rng, dict):
            clean = {k: rng[k] for k in ("min", "max") if re.fullmatch(r"\d{2}:\d{2}", str(rng.get(k, "")))}
            if clean:
                clean["strict"] = rng.get("strict") is True
                clean["label"] = str(rng.get("label", ""))[:40]
                out["range"] = clean
        if isinstance(st.get("date"), str):
            try:
                out["date"] = services.check_date(st["date"]).isoformat()
            except HTTPException:
                notes.append("La fecha elegida ya no es válida.")
        if out.get("date") and out.get("spec_id") and re.fullmatch(r"\d{2}:\d{2}", str(st.get("time", ""))):
            free = [s for s in services.slots_by_professional(db, out["spec_id"], date.fromisoformat(out["date"]),
                                                              out.get("pro_id")) if s["time"] == st["time"]]
            if free:
                out["time"], out["pro_id"] = st["time"], free[0]["professional_id"]
            else:
                notes.append(f"El horario de las {st['time']} acaba de ocuparse.")
        alias = str(st.get("alias", "")).strip()
        if 2 <= len(alias) <= 60 and not alias.startswith("#"):
            out["alias"] = alias
        if "phone" in st and re.fullmatch(r"(\d{10})?", str(st["phone"])):
            out["phone"] = st["phone"]
    elif flow in ("consult", "cancel"):
        code = parse_folio(norm(str(st.get("code", ""))))
        if code:
            out["code"] = code
            if check_value(st.get("grant"), code):
                out["grant"] = st["grant"]
    elif flow == "lead":
        alias = str(st.get("alias", "")).strip()
        if 2 <= len(alias) <= 60 and not alias.startswith("#"):
            out["alias"] = alias
        if "phone" in st and re.fullmatch(r"(\d{10})?", str(st["phone"])):
            out["phone"] = st["phone"]
    return out, notes


def _need(st: dict) -> str:
    if not st.get("spec_id"):
        return "spec"
    if st.get("want_pro") and not st.get("pro_id"):
        return "pro"
    if not st.get("date"):
        return "date"
    if not st.get("time"):
        return "time"
    if not st.get("alias"):
        return "alias"
    if "phone" not in st:
        return "phone"
    return "confirm"


def _drop(st: dict, *keys):
    for k in keys:
        st.pop(k, None)


# ------------------------------------------------------------------ componentes
def _spec_cards(db, only=None):
    items = []
    rows = only or db.execute("SELECT id,name,price,description FROM specialties WHERE active=1 ORDER BY id").fetchall()
    for s in rows:
        nxt = services.next_available(db, s["id"], max_days=14)
        pros = ", ".join(p["name"] for p in _pros(db, s["id"]))
        items.append({"title": s["name"], "subtitle": pros, "price": money(s["price"]), "icon": s["name"],
                      "meta": f"Próximo: {rel_day(date.fromisoformat(nxt['date']))} {nxt['time']}" if nxt else "Sin horarios próximos",
                      "value": f"#spec:{s['id']}"})
    return {"type": "cards", "items": items}


def _available_days(db, st, limit=7, start=None, end=None):
    out, day = [], start or date.today()
    last = min(end or date.today() + timedelta(days=services.MAX_DAYS_AHEAD),
               date.today() + timedelta(days=services.MAX_DAYS_AHEAD))
    while day <= last and len(out) < limit:
        if day.weekday() != 6:
            n = sum(1 for s in services.slots_by_professional(db, st["spec_id"], day, st.get("pro_id"))
                    if in_range(s["time"], st.get("range")))
            if n:
                out.append((day, n))
        day += timedelta(days=1)
    return out


def _spec_row(db, sid):
    return db.execute("SELECT id,name,price FROM specialties WHERE id=?", (sid,)).fetchone()


def _pro_name(db, pid):
    r = db.execute("SELECT name FROM professionals WHERE id=?", (pid,)).fetchone() if pid else None
    return r["name"] if r else None


def _render_book(db, st: dict, notes: list[str], intent="agendar", events=()) -> dict:
    step = _need(st)
    st["step"] = step
    note = " ".join(n for n in notes if n)
    note = (note + " ") if note else ""
    nav = [BACK_BTN, EXIT_BTN] if step != "spec" else [EXIT_BTN]
    events = list(events) + [("step", step)]
    spec = _spec_row(db, st["spec_id"]) if st.get("spec_id") else None
    rng = st.get("range")
    rng_txt = f" ({rng['label']})" if rng and rng.get("label") else ""

    if step == "spec":
        return R(f"{note}¿Qué especialidad necesitas?", buttons=[EXIT_BTN], state=st, ui=_spec_cards(db),
                 step=step, intent=intent, events=events)
    if step == "pro":
        pros = _pros(db, st["spec_id"])
        if st.get("gender"):
            pros = [p for p in pros if p["name"].startswith("Dra." if st["gender"] == "f" else "Dr. ")] or pros
        items = []
        for p in pros:
            nxt = services.next_available(db, st["spec_id"], max_days=21, professional_id=p["id"])
            items.append({"title": p["name"], "subtitle": spec["name"], "icon": "user", "value": f"#pro:{p['id']}",
                          "meta": f"Próximo: {rel_day(date.fromisoformat(nxt['date']))} {nxt['time']}" if nxt else "Sin horarios próximos"})
        items.append({"title": "Sin preferencia", "subtitle": "El primer horario disponible", "icon": "clock",
                      "value": "#pro:any"})
        return R(f"{note}¿Con qué especialista prefieres tu cita de {spec['name']}?", buttons=nav, state=st,
                 ui={"type": "cards", "items": items}, step=step, intent=intent, events=events)
    if step == "date":
        days = _available_days(db, st)
        if not days:
            events.append(("availability_error", "sin_dias"))
            extra = [{"label": "Quitar filtro de horario", "value": "#clear_range"}] if rng else []
            return R(f"{note}No encontré horarios disponibles para {spec['name']}{rng_txt} en las próximas semanas.",
                     buttons=extra + [{"label": "Elegir otra especialidad", "value": "#edit:spec"},
                                      {"label": "Hablar con recepción", "value": "humano"}],
                     state=st, step=step, intent=intent, events=events)
        who = _pro_name(db, st.get("pro_id"))
        items = [{"label": DOW[d.weekday()], "day": str(d.day), "month": MONTHS[d.month - 1],
                  "sub": f"{n} horario{'s' if n != 1 else ''}", "value": f"#date:{d.isoformat()}",
                  "today": d == date.today()} for d, n in days]
        extra = [] if st.get("pro_id") or len(_pros(db, st["spec_id"])) < 2 else \
            [{"label": "Elegir especialista", "value": "#pickpro"}]
        return R(f"{note}{spec['name']}{' con ' + who if who else ''} · {money(spec['price'])}. "
                 f"¿Qué día te acomoda{rng_txt}?", buttons=extra + nav, state=st,
                 ui={"type": "dates", "items": items}, step=step, intent=intent, events=events)
    if step == "time":
        day = date.fromisoformat(st["date"])
        slots = [s for s in services.slots_by_professional(db, st["spec_id"], day, st.get("pro_id"))
                 if in_range(s["time"], rng)]
        if not slots:
            events.append(("availability_error", "sin_horarios"))
            _drop(st, "date")
            who = _pro_name(db, st.get("pro_id"))
            why = f"{who} no tiene horarios libres el {fmt_day(day)}{rng_txt}." if who else \
                f"El {fmt_day(day)} ya no hay horarios libres{rng_txt}."
            return _render_book(db, st, [note + why], intent, events[:-1])
        groups: dict[int, dict] = {}
        for s in slots:
            g = groups.setdefault(s["professional_id"], {"professional": s["professional"], "items": []})
            g["items"].append({"label": s["time"], "value": f"#slot:{s['professional_id']}@{s['time']}"})
        return R(f"{note}Horarios libres el {fmt_day(day)}{rng_txt}. Elige el que prefieras:",
                 buttons=[{"label": "Otro día", "value": "#edit:date"}] + nav, state=st,
                 ui={"type": "slots", "groups": list(groups.values())}, step=step, intent=intent, events=events)
    if step == "alias":
        return R(f"{note}¿A nombre de quién registro la cita? Escribe un alias o nombre corto (sin datos médicos).",
                 buttons=nav, state=st, step=step, intent=intent, events=events, expects="alias")
    if step == "phone":
        return R(f"{note}Gracias, {st['alias'].rstrip('.')}. ¿Quieres dejar un teléfono de 10 dígitos para recordatorios?",
                 buttons=[{"label": "Omitir", "value": "#skip"}] + nav, state=st, step=step, intent=intent,
                 events=events, expects="phone")
    # confirm
    day = date.fromisoformat(st["date"])
    rows = [["Especialidad", spec["name"]], ["Especialista", _pro_name(db, st["pro_id"])],
            ["Fecha", fmt_day(day)], ["Hora", f"{st['time']} h"], ["Paciente", st["alias"]],
            ["Costo", f"{money(spec['price'])} · pago en recepción"]]
    return R(f"{note}Revisa los datos de tu cita:", state=st, step=step, intent=intent, events=events,
             ui={"type": "summary", "rows": rows,
                 "edits": [{"label": "Cambiar fecha", "value": "#edit:date"},
                           {"label": "Cambiar hora", "value": "#edit:time"},
                           {"label": "Cambiar especialidad", "value": "#edit:spec"}]},
             buttons=[{"label": "Confirmar cita", "value": "#confirm", "primary": True}, BACK_BTN, EXIT_BTN])


# ------------------------------------------------------------------ flujo de reserva
def _go_back(st: dict):
    step = _need(st)
    order = {"pro": ("want_pro", "pro_id"), "date": ("spec_id", "pro_id", "want_pro"), "time": ("date",),
             "alias": ("time",), "phone": ("alias",), "confirm": ("phone",)}
    _drop(st, *order.get(step, ()))


def _apply_entities(db, st: dict, ent: dict, notes: list[str]) -> bool:
    """Aplica entidades del mensaje como datos nuevos o correcciones. Devuelve True si cambió algo."""
    changed = False
    if ent["spec"] and ent["spec"]["id"] != st.get("spec_id"):
        st["spec_id"] = ent["spec"]["id"]
        _drop(st, "pro_id", "time", "want_pro")
        changed = True
    if ent["gender"]:
        st["gender"] = ent["gender"]
        changed = True
    if ent["pro"] and (not st.get("spec_id") or ent["pro"]["specialty_id"] == st["spec_id"]):
        st["spec_id"], st["pro_id"] = ent["pro"]["specialty_id"], ent["pro"]["id"]
        _drop(st, "time", "want_pro")
        changed = True
    if ent["range"]:
        st["range"] = ent["range"]
        _drop(st, "time")
        changed = True
    if ent["day"]:
        try:
            st["date"] = services.check_date(ent["day"].isoformat()).isoformat()
            _drop(st, "time")
        except HTTPException as e:
            notes.append(f"{e.detail} ({fmt_day(ent['day'])}).")
            _drop(st, "date", "time")
        changed = True
    if ent["asap"]:
        st["asap"] = True
        _drop(st, "date", "time")
        changed = True
    if ent["other_day"] and not ent["day"]:
        if st.get("date"):
            st["skip_after"] = st["date"]
        else:
            st["asap"] = True  # «dame otra opción» sin fecha: propone la más próxima
        _drop(st, "date", "time")
        changed = True
    elif ent["other_time"]:
        _drop(st, "time")
        changed = True
    if ent["time"]:
        st["want_time"] = ent["time"]
        changed = True
    return changed


def _resolve(db, st: dict, notes: list[str]):
    """Completa datos derivados: preferencia de especialista, «lo antes posible», «otro día», hora pedida."""
    if st.get("spec_id") and st.get("gender") and not st.get("pro_id"):
        pros = [p for p in _pros(db, st["spec_id"]) if p["name"].startswith("Dra." if st["gender"] == "f" else "Dr. ")]
        if len(pros) == 1:
            st["pro_id"] = pros[0]["id"]
        elif not pros:
            notes.append(f"No tenemos {'una doctora' if st['gender'] == 'f' else 'un doctor'} en esta especialidad; "
                         "te muestro las opciones disponibles.")
        else:
            st["want_pro"] = True
        st.pop("gender", None)
    after = st.pop("skip_after", None)
    if st.get("spec_id") and not st.get("date") and (st.pop("asap", False) or after):
        start = date.fromisoformat(after) + timedelta(days=1) if after else date.today()
        days = _available_days(db, st, limit=1, start=start)
        if days:
            st["date"] = days[0][0].isoformat()
            if after:
                notes.append(f"Te propongo el {fmt_day(days[0][0])}.")
        else:
            notes.append("No encontré otra fecha disponible.")
    want = st.pop("want_time", None)
    if want and st.get("spec_id") and st.get("date"):
        free = [s for s in services.slots_by_professional(db, st["spec_id"], date.fromisoformat(st["date"]),
                                                          st.get("pro_id")) if s["time"] == want]
        if free:
            st["time"], st["pro_id"] = want, free[0]["professional_id"]
        else:
            notes.append(f"Las {want} no está disponible ese día.")
    elif want:
        st["range"] = {"min": want, "strict": False, "label": f"desde las {want}"}


def _book_flow(db, raw: str, msg: str, st: dict, hint: str, notes: list[str]) -> dict:
    events = []
    m = re.fullmatch(r"#(\w+)(?::(.+))?", msg)
    cmd, arg = (m.group(1), m.group(2)) if m else (None, None)

    if msg in BACK:
        _go_back(st)
        return _render_book(db, st, notes)
    if cmd == "resume":
        return _render_book(db, st, notes)
    if cmd == "spec" and arg and arg.isdigit():
        if _spec_row(db, int(arg)):
            st["spec_id"] = int(arg)
            _drop(st, "pro_id", "time", "want_pro")
    elif cmd == "pickpro":
        st["want_pro"] = True
        _drop(st, "pro_id", "time")
    elif cmd == "pro":
        st.pop("want_pro", None)
        _drop(st, "time")
        if arg == "any":
            st.pop("pro_id", None)
        elif arg and arg.isdigit() and any(p["id"] == int(arg) for p in _pros(db, st.get("spec_id"))):
            st["pro_id"] = int(arg)
    elif cmd == "date" and arg:
        try:
            st["date"] = services.check_date(arg).isoformat()
            _drop(st, "time")
        except HTTPException as e:
            notes.append(f"{e.detail}.")
    elif cmd == "slot" and arg and re.fullmatch(r"\d+@\d{2}:\d{2}", arg):
        pid, t = arg.split("@")
        st["pro_id"], st["want_time"] = int(pid), t
    elif cmd == "edit" and arg in ("spec", "date", "time", "alias", "phone"):
        _drop(st, *{"spec": ("spec_id", "pro_id", "date", "time", "want_pro"), "date": ("date", "time"),
                    "time": ("time",), "alias": ("alias",), "phone": ("phone",)}[arg])
    elif cmd == "clear_range":
        _drop(st, "range")
    elif cmd == "skip" and hint == "phone":
        st["phone"] = ""
    elif cmd == "confirm" or (hint == "confirm" and msg in YES):
        if _need(st) != "confirm":
            return _render_book(db, st, notes + ["Faltan algunos datos."])
        try:
            appt = services.book_appointment(db, st["spec_id"], st["date"], st["time"], st["alias"],
                                             st.get("phone", ""), channel="chatbot", professional_id=st["pro_id"])
        except HTTPException as e:
            _drop(st, "time")
            return _render_book(db, st, [f"No se pudo reservar: {e.detail}. Elige otro horario."],
                                events=[("availability_error", "conflicto")])
        d = date.fromisoformat(appt["date"])
        rows = [["Especialidad", appt["specialty"]], ["Especialista", appt["professional"]],
                ["Fecha", fmt_day(d)], ["Hora", f"{appt['time']} h"], ["Costo", money(appt["price"])]]
        return R("✅ ¡Tu cita quedó confirmada! Guarda tu folio y tu PIN: los necesitarás para consultarla o "
                 "cancelarla. Por seguridad, el PIN solo se muestra esta vez.",
                 buttons=[{"label": "¿Qué debo llevar?", "value": "que llevo"},
                          {"label": "Ubicación", "value": "ubicacion"}, {"label": "Nueva consulta", "value": "hola"}],
                 ui={"type": "confirmation", "code": appt["code"], "pin": appt["pin"], "rows": rows,
                     "ics": f"/api/appointments/{appt['code']}/ics?pin={appt['pin']}"},
                 intent="agendar", action={"type": "folio", "code": appt["code"]},
                 events=[("step", "done"), ("booking_completed", appt["specialty"])])
    elif hint == "alias":
        ent = extract(db, msg, st.get("spec_id"))
        if has_booking_entity(ent):
            _apply_entities(db, st, ent, notes)
        else:
            alias = raw.strip()
            if not 2 <= len(alias) <= 60 or alias.startswith("#") or re.search(r"[?¿@]|\d{3,}", alias):
                return _render_book(db, st, ["Escribe solo un alias o nombre corto (2 a 60 caracteres)."])
            st["alias"] = alias
    elif hint == "phone":
        digits = re.sub(r"\D", "", raw)
        if re.fullmatch(r"(omitir|no|sin telefono|no gracias|prefiero no)", msg):
            st["phone"] = ""
        elif len(digits) == 10:
            st["phone"] = digits
        else:
            ent = extract(db, msg, st.get("spec_id"))
            if not has_booking_entity(ent):
                return _render_book(db, st, ["El teléfono debe tener 10 dígitos, o pulsa «Omitir»."])
            _apply_entities(db, st, ent, notes)
    else:
        ent = extract(db, msg, st.get("spec_id"), bare_time=(hint == "time"))
        if not _apply_entities(db, st, ent, notes):
            events.append(("fallback", sanitize(msg)))
            notes.append("No identifiqué ese dato.")
    _resolve(db, st, notes)
    return _render_book(db, st, notes, events=events)


# ------------------------------------------------------------------ consulta / cancelación verificada
def _appointment_ui(a: dict) -> dict:
    d = date.fromisoformat(a["date"])
    return {"type": "appointment", "code": a["code"], "status": a["status"],
            "rows": [["Especialidad", a["specialty"]], ["Especialista", a["professional"]],
                     ["Fecha", fmt_day(d)], ["Hora", f"{a['time']} h"]]}


def _access_flow(db, raw: str, msg: str, st: dict, session: str) -> dict:
    flow = st["flow"]
    nav = [EXIT_BTN]
    if msg == "#cancel_this" and st.get("grant"):
        st["flow"] = flow = "cancel"
    verb = "consultar" if flow == "consult" else "cancelar"
    it = "consultar" if flow == "consult" else "cancelar"
    if flow == "cancel" and st.get("grant") and msg in ("#cancel_yes",):
        try:
            services.cancel_by_code(db, st["code"])
        except HTTPException as e:
            return R(f"{e.detail}.", intent="cancelar")
        return R(f"Listo, la cita {st['code']} fue cancelada y el horario quedó libre para otra persona. "
                 "¿Quieres agendar una nueva?", buttons=[{"label": "Agendar cita", "value": "agendar"}] + MAIN_MENU[1:3],
                 intent="cancelar", events=[("cancel_completed", "")])
    if flow == "cancel" and st.get("grant"):
        # El acceso ya fue verificado con PIN y está respaldado por un token firmado de corta duración.
        row = db.execute(services.APPT_SELECT + " WHERE a.code=?", (st["code"],)).fetchone()
        if not row:
            return R(services.ACCESS_DENIED + ".", intent="cancelar")
        ui = _appointment_ui(dict(row))
        if row["status"] != "confirmada":
            return R(f"Esta cita está {row['status']} y ya no puede cancelarse.", ui=ui, intent="cancelar")
        return R("¿Confirmas que quieres cancelar esta cita? Esta acción no se puede deshacer.",
                 buttons=[{"label": "Sí, cancelar cita", "value": "#cancel_yes", "danger": True},
                          {"label": "No, conservarla", "value": "#salir"}], state=st, ui=ui, intent="cancelar")
    if not st.get("code"):
        code = parse_folio(msg)
        if not code:
            return R(f"Para {verb} tu cita escribe tu folio (formato MB-XXXXXXXX).", buttons=nav, state=st,
                     intent=it, expects="folio")
        st["code"] = code
        return R(f"Folio {code}. Ahora escribe el PIN de 6 dígitos que recibiste al reservar.", buttons=nav,
                 state=st, intent=it, expects="pin")
    pin = re.sub(r"\D", "", raw)
    if len(pin) != 6:
        new_code = parse_folio(msg)
        if new_code:
            st["code"] = new_code
            return R(f"Folio {new_code}. Escribe el PIN de 6 dígitos.", buttons=nav, state=st, expects="pin",
                     intent=it)
        return R("El PIN tiene 6 dígitos. Escríbelo de nuevo.", buttons=nav, state=st, expects="pin",
                 intent=it)
    try:
        a = services.verify_access(db, st["code"], pin, client=f"chat:{session}")
    except HTTPException as e:
        if e.status_code == 429:
            return R(f"{e.detail}", intent=it, events=[("access_blocked", "")])
        return R(f"{e.detail}. Revisa ambos datos e inténtalo de nuevo.", buttons=nav, state=st, expects="pin",
                 intent=it, events=[("access_failed", "")])
    grant = sign_value(a["code"])
    if flow == "consult":
        btns = [{"label": "Cancelar esta cita", "value": "#cancel_this"}] if a["status"] == "confirmada" else []
        return R(f"Encontré tu cita. Estado: {a['status']}.", buttons=btns + MAIN_MENU[:3],
                 state={"flow": "consult", "code": a["code"], "grant": grant}, ui=_appointment_ui(a),
                 intent="consultar", events=[("lookup_completed", "")])
    st["grant"] = grant
    return _access_flow(db, raw, "#show", st, session)


# ------------------------------------------------------------------ atención humana
def _lead_flow(db, raw: str, msg: str, st: dict) -> dict:
    nav = [EXIT_BTN]
    if not st.get("alias"):
        alias = raw.strip()
        if msg.startswith("#") or not alias or detect_intent(msg) == "humano":
            return R("Con gusto te comunico con recepción. ¿Cómo te llamas? (un alias es suficiente)", buttons=nav,
                     state=st, intent="humano", expects="alias")
        if not 2 <= len(alias) <= 60:
            return R("El nombre debe tener entre 2 y 60 caracteres.", buttons=nav, state=st, expects="alias",
                     intent="humano")
        st["alias"] = alias
        return R(f"Gracias, {alias.rstrip('.')}. ¿A qué teléfono de 10 dígitos pueden llamarte? También puedes omitirlo.",
                 buttons=[{"label": "Omitir", "value": "#skip"}] + nav, state=st, expects="phone", intent="humano")
    if "phone" not in st:
        digits = re.sub(r"\D", "", raw)
        if msg in ("#skip", "omitir", "no"):
            st["phone"] = ""
        elif len(digits) == 10:
            st["phone"] = digits
        else:
            return R("El teléfono debe tener 10 dígitos, o pulsa «Omitir».",
                     buttons=[{"label": "Omitir", "value": "#skip"}] + nav, state=st, expects="phone",
                     intent="humano")
        return R("¿Sobre qué tema necesitas ayuda?", state=st, intent="humano",
                 buttons=[{"label": v, "value": f"#topic:{k}"} for k, v in CONTACT_TOPICS.items()] + nav)
    m = re.fullmatch(r"#topic:(\w+)", msg)
    topic = m.group(1) if m and m.group(1) in CONTACT_TOPICS else None
    if not topic:
        return R("Elige un tema de la lista.", state=st, intent="humano",
                 buttons=[{"label": v, "value": f"#topic:{k}"} for k, v in CONTACT_TOPICS.items()] + nav)
    services.create_contact_request(db, st["alias"], st.get("phone", ""), topic)
    when = "te llamará" if st.get("phone") else "atenderá tu solicitud"
    return R(f"Listo, registré tu solicitud ({CONTACT_TOPICS[topic].lower()}). Recepción {when} en horario de "
             "atención. ¿Te ayudo con algo más?", intent="humano", events=[("human_request", topic)])


# ------------------------------------------------------------------ respuestas de un turno
def _greeting(page: str) -> str:
    from datetime import datetime
    h = datetime.now().hour
    hello = "Hola" if h < 6 else "Buenos días" if h < 12 else "Buenas tardes" if h < 19 else "Buenas noches"
    ctx = " ¿Te ayudo a encontrar un horario?" if page == "reservar" else " ¿En qué te ayudo hoy?"
    return (f"{hello}. Soy MediBot, la recepción virtual de {CLINIC['name']}. Puedo mostrarte disponibilidad, "
            f"precios y agendar, consultar o cancelar tu cita. Escríbeme con naturalidad, por ejemplo: "
            f"«quiero cardiología el viernes después de las 11».{ctx}")


def _single_turn(db, raw: str, msg: str, page: str, session: str = "") -> dict:
    intent = detect_intent(msg)
    if intent == "emergencia":
        return R(f"⚠️ Si es una emergencia, llama al {CLINIC['emergency_number']} o acude de inmediato al servicio "
                 "de urgencias más cercano. Este asistente no puede atender urgencias médicas.",
                 ui={"type": "emergency", "number": CLINIC["emergency_number"]},
                 buttons=[{"label": "Ver ubicación", "value": "ubicacion"}], intent=intent)
    if intent == "salud":
        gen = db.execute("SELECT id FROM specialties WHERE active=1 ORDER BY id LIMIT 1").fetchone()
        return R("Entiendo tu preocupación, pero no puedo dar diagnósticos, interpretar síntomas ni recomendar "
                 "medicamentos. Lo indicado es que te valore un especialista. Si los síntomas son graves, llama al "
                 f"{CLINIC['emergency_number']}.",
                 buttons=([{"label": "Agendar valoración", "value": f"#start:{gen['id']}"}] if gen else []) +
                 [{"label": "Ver especialidades", "value": "especialidades"}], intent=intent)

    ent = extract(db, msg)
    if ent["folio"] and intent in ("consultar", "cancelar", "otro"):
        flow = "cancel" if intent == "cancelar" else "consult"
        return _access_flow(db, raw, msg, {"flow": flow}, session)

    m = re.fullmatch(r"#start:(\d+)", msg)
    if m and _spec_row(db, int(m.group(1))):
        return _render_book(db, {"flow": "book", "spec_id": int(m.group(1))}, [])

    booking = intent == "agendar" or (intent in ("otro", "especialidades", "disponibilidad", "horarios") and (
        (ent["spec"] or ent["pro"]) and (ent["day"] or ent["time"] or ent["range"] or ent["asap"] or
                                         any(w in msg for w in WANT))))
    if intent == "disponibilidad" and (ent["spec"] or ent["pro"]) and not ent["week"]:
        booking = True
    if intent == "disponibilidad" and not (ent["spec"] or ent["pro"]) and (ent["asap"] or ent["day"] or ent["range"]):
        booking = True
    if booking:
        st, notes = {"flow": "book"}, []
        _apply_entities(db, st, ent, notes)
        _resolve(db, st, notes)
        if not st.get("spec_id") and (ent["day"] or ent["range"] or ent["asap"]):
            pref = " ".join(x for x in (rel_day(ent["day"]) if ent["day"] else "", ent["range"]["label"] if ent["range"]
                                        else "", "lo antes posible" if ent["asap"] else "") if x)
            notes.insert(0, f"Anoté: {pref}.")
        return _render_book(db, st, notes, intent="agendar" if intent != "disponibilidad" else intent)

    if intent == "disponibilidad":
        start, end = date.today(), date.today() + timedelta(days=(5 - date.today().weekday()) % 7)
        if not ent["week"]:
            end = date.today() + timedelta(days=13)
        items = []
        for s in db.execute("SELECT id,name,price FROM specialties WHERE active=1 ORDER BY id").fetchall():
            days = _available_days(db, {"spec_id": s["id"]}, limit=14, start=start, end=end)
            total = sum(n for _, n in days)
            items.append({"title": s["name"], "icon": s["name"], "price": money(s["price"]),
                          "subtitle": f"{total} horarios · {len(days)} días" if days else "Sin horarios en este periodo",
                          "meta": f"Desde {rel_day(days[0][0])}" if days else "", "value": f"#start:{s['id']}"})
        period = "esta semana" if ent["week"] else "en las próximas dos semanas"
        return R(f"Esta es la disponibilidad {period}. Toca una especialidad para ver días y horarios.",
                 ui={"type": "cards", "items": items}, intent=intent)

    if intent == "precios":
        rows = db.execute("SELECT id,name,price,description FROM specialties WHERE active=1 ORDER BY price").fetchall()
        if ent["spec"]:
            s = ent["spec"]
            return R(f"La consulta de {s['name']} cuesta {money(s['price'])} y se paga en recepción.",
                     ui=_spec_cards(db, [s]), buttons=[{"label": f"Agendar {s['name']}", "value": f"#start:{s['id']}"}]
                     + MAIN_MENU[1:3], intent=intent)
        if re.search(r"economic|barat|menor precio|menos cuesta", msg) and rows:
            s = rows[0]
            return R(f"La especialidad más económica es {s['name']}: {money(s['price'])} por consulta.",
                     ui=_spec_cards(db, [s]), intent=intent)
        if re.search(r"mas car[ao]|mas costos", msg) and rows:
            s = rows[-1]
            return R(f"La consulta con mayor costo es {s['name']}: {money(s['price'])}.", ui=_spec_cards(db, [s]),
                     intent=intent)
        lines = ", ".join(f"{r['name']} {money(r['price'])}" for r in rows)
        return R(f"Estos son nuestros precios por consulta: {lines}. {CLINIC['payment_policy']}",
                 ui=_spec_cards(db), intent=intent)
    if intent == "especialidades":
        if ent["spec"]:
            s = ent["spec"]
            return R(f"{s['name']}: {s['description']}", ui=_spec_cards(db, [s]),
                     buttons=[{"label": f"Agendar {s['name']}", "value": f"#start:{s['id']}"}] + MAIN_MENU[1:3],
                     intent=intent)
        rows = db.execute("SELECT name FROM specialties WHERE active=1 ORDER BY id").fetchall()
        return R(f"Contamos con {len(rows)} especialidades: {', '.join(r['name'] for r in rows)}. ¿Cuál te interesa?",
                 ui=_spec_cards(db), intent=intent)
    if intent == "horarios":
        hours = services.clinic_hours(db)
        return R("Horario general de atención:", ui={"type": "summary", "rows": [list(h) for h in hours]},
                 buttons=[{"label": "Ver disponibilidad", "value": "disponibilidad"}] + MAIN_MENU[:1], intent=intent)
    if intent == "pagos":
        return R(f"Aceptamos {', '.join(CLINIC['payment_methods'])}. {CLINIC['payment_policy']} {CLINIC['insurance']}",
                 buttons=[{"label": "Ver precios", "value": "precios"}, {"label": "Agendar cita", "value": "agendar"}],
                 intent=intent)
    if intent == "ubicacion":
        return R(f"Estamos en {CLINIC['address']} {CLINIC['parking']} Teléfono: {CLINIC['phone']}.",
                 buttons=[{"label": "Horarios", "value": "horarios"}, {"label": "Agendar cita", "value": "agendar"}],
                 intent=intent)
    if intent == "preparacion":
        return R(CLINIC["arrival"], intent=intent)
    if intent == "consultar":
        return _access_flow(db, raw, msg, {"flow": "consult"}, session)
    if intent == "cancelar":
        return _access_flow(db, raw, msg, {"flow": "cancel"}, session)
    if intent == "humano":
        return _lead_flow(db, raw, msg, {"flow": "lead"})
    if intent == "saludo":
        return R(_greeting(page), intent=intent)
    if intent == "despedida":
        return R("¡Con gusto! Si necesitas algo más, aquí estaré. Que tengas un excelente día.", intent=intent)
    return R("Disculpa, no entendí tu mensaje. Puedes escribir, por ejemplo, «precios», «¿qué tienen esta semana?» "
             "o «quiero dermatología mañana por la tarde». También puedes elegir una opción:", intent="otro",
             events=[("fallback", sanitize(msg))])


# ------------------------------------------------------------------ punto de entrada
def handle(db, message: str, state: dict | None, page: str = "", session: str = "") -> dict:
    raw = str(message).strip()[:500]
    msg = norm(raw)
    st, notes = _clean_state(db, state if isinstance(state, dict) else {})
    hint = state.get("step") if isinstance(state, dict) else None

    if msg in EXIT:
        out = R("Listo, cancelé el proceso. ¿En qué más te ayudo?", intent="salir",
                events=[("abandon", (state or {}).get("step", "")) if st.get("flow") == "book" else ("exit", "")])
    elif st.get("flow") and (is_emergency(msg) or (st["flow"] != "book" and detect_intent(msg) == "salud")):
        # Una emergencia (o una pregunta de salud fuera de la reserva) interrumpe cualquier proceso abierto,
        # por ejemplo una consulta de cita que esperaba el PIN.
        out = _single_turn(db, raw, msg, page, session)
    elif st.get("flow") == "book":
        intent = detect_intent(msg)
        ent = None if msg.startswith("#") else extract(db, msg, st.get("spec_id"))
        # Mientras escribe su alias/teléfono, solo una pregunta explícita («¿cuánto cuesta?») cambia de tema.
        typing_data = _need(st) in ("alias", "phone") and not re.search(r"[?¿]", raw)
        if intent in ("consultar", "cancelar", "humano") and not (ent and has_booking_entity(ent)) \
                and not typing_data:
            out = _single_turn(db, raw, msg, page, session)  # cambio de intención: abandona la reserva
            out["events"].insert(0, ("abandon", _need(st)))
        elif intent in ("precios", "horarios", "ubicacion", "pagos", "preparacion", "salud", "despedida") \
                and not (ent and has_booking_entity(ent)) and not typing_data:
            out = _single_turn(db, raw, msg, page, session)  # pregunta lateral: conserva la reserva
            out["state"] = {**st, "step": _need(st)}
            out["buttons"] = [{"label": "Continuar mi cita", "value": "#resume", "primary": True}] + out["buttons"][:3]
        else:
            out = _book_flow(db, raw, msg, st, _need(st), notes)  # el paso lo decide el servidor
    elif st.get("flow") in ("consult", "cancel"):
        intent = detect_intent(msg)
        if intent in ("agendar", "humano", "precios", "disponibilidad") and not parse_folio(msg) \
                and not re.fullmatch(r"\d{6}", msg) and not msg.startswith("#"):
            out = _single_turn(db, raw, msg, page, session)
        else:
            out = _access_flow(db, raw, msg, st, session)
    elif st.get("flow") == "lead":
        out = _lead_flow(db, raw, msg, st)
    else:
        out = _single_turn(db, raw, msg, page, session)
    return out
