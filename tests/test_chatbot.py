from datetime import date, timedelta

from conftest import next_weekday


def say(client, msg, state=None, session="t-1"):
    r = client.post("/api/chat", json={"message": msg, "state": state or {}, "session": session})
    assert r.status_code == 200
    out = r.json()
    assert "events" not in out  # las métricas internas no se exponen al navegador
    return out


def book_by_chat(client, spec="#spec:2", alias="Paciente Demo"):
    out = say(client, "quiero agendar una cita")
    out = say(client, spec, out["state"])
    first = out["ui"]["items"][0]["value"]
    out = say(client, first, out["state"])
    slot = out["ui"]["groups"][0]["items"][0]["value"]
    out = say(client, slot, out["state"])
    out = say(client, alias, out["state"])
    out = say(client, "#skip", out["state"])
    assert out["ui"]["type"] == "summary" and out["progress"]["current"] == 5
    return say(client, "#confirm", out["state"])


# ---------------------------------------------------------------- básicos
def test_saludo_y_menu(client):
    out = say(client, "Hola")
    assert "MediBot" in out["reply"] and out["buttons"]


def test_precios_y_especialidades(client):
    assert "$450" in say(client, "¿Cuáles son los precios?")["reply"]
    out = say(client, "especialidades")
    assert "Cardiología" in out["reply"] and out["ui"]["type"] == "cards"


def test_emergencia_no_diagnostica(client):
    out = say(client, "Creo que es una emergencia, dolor de pecho")
    assert "911" in out["reply"] and out["intent"] == "emergencia" and out["ui"]["type"] == "emergency"
    out = say(client, "me duele la cabeza, ¿qué me tomo?")
    assert "no puedo dar diagnósticos" in out["reply"].lower() and out["intent"] == "salud"


def test_emergencia_interrumpe_una_reserva(client):
    out = say(client, "quiero cardiología el viernes")
    out = say(client, "no puedo respirar", out["state"])
    assert out["intent"] == "emergencia" and out["state"] == {}


def test_fallback(client):
    out = say(client, "asdf qwerty")
    assert out["intent"] == "otro" and out["buttons"]


# ---------------------------------------------------------------- lenguaje natural
def test_lenguaje_natural_salta_pasos(client):
    out = say(client, "Quiero una cita con cardiología el viernes")
    assert out["state"]["step"] == "time" and out["state"]["spec_id"] == 2 and out["ui"]["type"] == "slots"
    out = say(client, "a las 10", out["state"])
    assert out["state"]["step"] == "alias" and out["state"]["time"] == "10:00"


def test_rango_horario_y_fecha_relativa(client):
    out = say(client, "¿Tienen algo mañana después de las once?")
    assert out["state"]["step"] == "spec" and out["state"]["range"]["min"] == "11:00"
    out = say(client, "#spec:3", out["state"])
    tomorrow = date.today() + timedelta(days=1)
    if tomorrow.weekday() == 6:
        assert out["state"]["step"] == "date"
    else:
        times = [i["label"] for g in out["ui"]["groups"] for i in g["items"]]
        assert times and all(t > "11:00" for t in times)


def test_preferencia_de_doctora(client):
    out = say(client, "quiero cardiología")
    out = say(client, "prefiero con la doctora", out["state"])
    assert out["state"]["pro_id"]
    for g in (out["ui"] or {}).get("groups", []):
        assert g["professional"] == "Dra. Laura Canché"


def test_correccion_de_fecha_y_otra_opcion(client):
    out = say(client, "quiero dermatología el lunes")
    assert date.fromisoformat(out["state"]["date"]).weekday() == 0
    out = say(client, "mejor cámbialo al sábado", out["state"])
    saturday = out["state"]["date"]
    assert date.fromisoformat(saturday).weekday() == 5
    out = say(client, "no puedo ese día, dame otra opción", out["state"])
    assert out["state"]["date"] > saturday and "Te propongo" in out["reply"]


def test_lo_antes_posible(client):
    out = say(client, "Quiero una cita lo antes posible")
    assert out["state"]["step"] == "spec"
    out = say(client, "#spec:5", out["state"])
    assert out["state"]["step"] == "time" and out["state"]["date"]


def test_mas_economica_y_semana(client):
    out = say(client, "¿Cuál es la especialidad más económica?")
    assert "Medicina general" in out["reply"]
    out = say(client, "¿Qué tienen disponible esta semana?")
    assert out["intent"] == "disponibilidad" and out["ui"]["type"] == "cards"


def test_preguntas_frecuentes(client):
    assert "$650" in say(client, "¿cuánto cuesta dermatología?")["reply"]
    assert say(client, "¿aceptan tarjeta?")["intent"] == "pagos"
    assert say(client, "¿dónde están?")["intent"] == "ubicacion"
    assert "Psicología" in say(client, "¿cuándo hay lugar para psicología?")["reply"]


def test_parse_day_y_periodos():
    from app.chatbot import parse_day, parse_range
    base = date(2026, 11, 23)  # lunes
    assert parse_day("manana", base) == date(2026, 11, 24)
    assert parse_day("pasado manana", base) == date(2026, 11, 25)
    assert parse_day("el viernes", base) == date(2026, 11, 27)
    assert parse_day("el lunes", base) == date(2026, 11, 30)
    assert parse_day("25/12", base) == date(2026, 12, 25)
    assert parse_day("en la manana", base) is None
    assert parse_day("manana por la manana", base) == date(2026, 11, 24)
    assert parse_range("por la manana")[0]["max"] == "12:00"
    assert parse_range("despues de las once")[0] == {"min": "11:00", "strict": True, "label": "después de las 11:00"}
    assert parse_range("antes de las 4")[0]["max"] == "16:00"


# ---------------------------------------------------------------- máquina de estados
def test_pregunta_lateral_conserva_la_reserva(client):
    out = say(client, "quiero cardiología el viernes")
    state = out["state"]
    out = say(client, "¿cuánto cuesta?", state)
    assert out["intent"] == "precios" and out["state"]["spec_id"] == 2
    assert out["buttons"][0]["value"] == "#resume"
    out = say(client, "#resume", out["state"])
    assert out["state"]["step"] == "time"


def test_regresar_y_cambio_de_intencion(client):
    out = say(client, "quiero cardiología el viernes")
    out = say(client, "#back", out["state"])
    assert out["state"]["step"] == "date"
    out = say(client, "mejor quiero consultar mi cita", out["state"])
    assert out["intent"] == "consultar" and out["state"]["flow"] == "consult"


def test_estado_manipulado_se_revalida(client):
    fake = {"flow": "book", "step": "confirm", "spec_id": 999, "date": "2020-01-01", "time": "03:00",
            "alias": "X" * 80, "phone": "abc"}
    out = say(client, "#confirm", fake)
    assert out["state"]["step"] == "spec" and "spec_id" not in out["state"]
    fake = {"flow": "cancel", "code": "MB-AAAAAAAA", "grant": "MB-AAAAAAAA|9999999999|deadbeef"}
    out = say(client, "#cancel_yes", fake)
    assert "cancelada" not in out["reply"]


def test_horario_ocupado_durante_la_conversacion(client):
    out = say(client, "quiero dermatología el viernes a las 10")
    state = out["state"]
    assert state["time"] == "10:00"
    day = state["date"]
    client.post("/api/appointments", json={"specialty_id": 3, "date": day, "time": "10:00", "alias": "Otra persona"})
    out = say(client, "Ana P.", state)
    assert out["state"]["step"] == "time" and "acaba de ocuparse" in out["reply"]


# ---------------------------------------------------------------- reserva, consulta y cancelación
def test_reserva_completa_consulta_y_cancelacion_verificada(client):
    out = book_by_chat(client)
    conf = out["ui"]
    assert conf["type"] == "confirmation" and conf["code"].startswith("MB-") and len(conf["pin"]) == 6
    assert out["action"]["code"] == conf["code"] and f"pin={conf['pin']}" in conf["ics"]
    code, pin = conf["code"], conf["pin"]

    out = say(client, "Ya tengo un folio y quiero consultar mi cita")
    out = say(client, code, out["state"])
    assert out["expects"] == "pin"
    out = say(client, "000000", out["state"])
    assert "No encontramos" in out["reply"]
    out = say(client, pin, out["state"])
    assert out["ui"]["type"] == "appointment" and out["ui"]["status"] == "confirmada"
    assert "pin" not in str(out["state"]).lower() or "grant" in out["state"]

    out = say(client, "#cancel_this", out["state"])  # usa el acceso verificado, sin volver a pedir PIN
    assert out["buttons"][0]["value"] == "#cancel_yes"
    out = say(client, "#cancel_yes", out["state"])
    assert "fue cancelada" in out["reply"]
    rows = client.get("/api/appointments/" + code, params={"pin": pin}).json()
    assert rows["status"] == "cancelada"


def test_cancelar_con_folio_en_el_mensaje(client):
    conf = book_by_chat(client, "#spec:4")["ui"]
    out = say(client, f"quiero cancelar la cita {conf['code']}")
    assert out["expects"] == "pin"
    out = say(client, conf["pin"], out["state"])
    out = say(client, "#cancel_yes", out["state"])
    assert "fue cancelada" in out["reply"]
    out = say(client, f"quiero cancelar la cita {conf['code']}")
    out = say(client, conf["pin"], out["state"])
    assert "no puede cancelarse" in out["reply"]


def test_lead_va_a_la_bandeja_de_recepcion(admin):
    out = say(admin, "quiero hablar con recepción")
    out = say(admin, "Lead Demo", out["state"])
    out = say(admin, "9811234567", out["state"])
    out = say(admin, "#topic:pagos", out["state"])
    assert "registré tu solicitud" in out["reply"]
    reqs = admin.get("/api/admin/requests").json()
    assert reqs[0]["alias"] == "Lead Demo" and reqs[0]["status"] == "pendiente"
    assert admin.post(f"/api/admin/requests/{reqs[0]['id']}/status", json={"status": "atendida"}).status_code == 200
    cust = admin.get("/api/admin/customers", params={"q": "Lead Demo"}).json()[0]
    assert cust["stage"] == "contactado"
    assert admin.get("/api/admin/dashboard").json()["requests"] == 0


def test_metricas_del_asistente(admin):
    book_by_chat(admin)
    say(admin, "xyzzy 123", session="t-2")
    m = admin.get("/api/admin/chat-metrics").json()
    assert m["bookings"] >= 1 and m["conversations"] >= 2 and m["conversion"] > 0
    assert any(f["step"] == "done" and f["sessions"] >= 1 for f in m["funnel"])
    assert any("xyzzy ###" == t["label"] for t in m["top_fallback"])  # texto anonimizado
