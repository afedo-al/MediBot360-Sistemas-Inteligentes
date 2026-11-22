import threading
from datetime import date, timedelta

from conftest import next_weekday


def book(client, **kw):
    body = {"specialty_id": 1, "date": next_weekday(2), "time": "09:00", "alias": "Alias Demo"}
    body.update(kw)
    return client.post("/api/appointments", json=body)


def test_rutas_panel_y_portal(client):
    assert "admin.js" in client.get("/").text          # la raíz abre el sistema administrativo
    assert "home.js" in client.get("/sitio").text      # el portal público vive en /sitio
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/"
    assert len(client.get("/api/specialties").json()) == 6


def test_crear_duplicado_consultar_cancelar_liberar(client):
    r = book(client)
    assert r.status_code == 201
    code, pin = r.json()["code"], r.json()["pin"]
    assert len(pin) == 6 and pin.isdigit()
    assert book(client).status_code == 409
    got = client.get(f"/api/appointments/{code}", params={"pin": pin})
    assert got.status_code == 200 and got.json()["status"] == "confirmada"
    assert "alias" not in got.json() and "phone" not in got.json()
    assert client.post(f"/api/appointments/{code}/cancel", json={"pin": pin}).status_code == 200
    assert client.post(f"/api/appointments/{code}/cancel", json={"pin": pin}).status_code == 409  # ya cancelada
    times = [s["time"] for s in client.get("/api/slots", params={"specialty_id": 1, "date": next_weekday(2)}).json()]
    assert "09:00" in times
    assert book(client).status_code == 201


def test_validaciones(client):
    assert book(client, date=(date.today() - timedelta(days=1)).isoformat()).status_code == 400
    d = date.today()
    while d.weekday() != 6:
        d += timedelta(days=1)
    assert book(client, date=d.isoformat()).status_code == 400
    assert book(client, date=(date.today() + timedelta(days=90)).isoformat()).status_code == 400
    assert book(client, time="03:00").status_code == 409
    assert book(client, alias="x").status_code == 422
    assert book(client, specialty_id=99).status_code == 404


def test_pin_incorrecto_no_revela_existencia(client):
    code = book(client).json()["code"]
    wrong = client.get(f"/api/appointments/{code}", params={"pin": "000000"})
    missing = client.get("/api/appointments/MB-NOEXISTE", params={"pin": "000000"})
    assert wrong.status_code == missing.status_code == 404
    assert wrong.json()["detail"] == missing.json()["detail"]
    assert client.post(f"/api/appointments/{code}/cancel", json={"pin": "123"}).status_code == 404


def test_limite_de_intentos(client):
    r = book(client).json()
    for _ in range(5):
        client.get(f"/api/appointments/{r['code']}", params={"pin": "999999"})
    blocked = client.get(f"/api/appointments/{r['code']}", params={"pin": r["pin"]})
    assert blocked.status_code == 429


def test_disponibilidad_real_por_especialista(client):
    day = next_weekday(1)
    while date.fromisoformat(day).weekday() > 4:  # el Dr. Pech atiende de lunes a viernes
        day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    rows = client.get("/api/slots", params={"specialty_id": 1, "date": day, "detailed": True}).json()
    at_noon = {r["professional"] for r in rows if r["time"] == "12:00"}
    assert at_noon == {"Dra. Elena Rojas", "Dr. Andrés Pech"}
    pech = next(r["professional_id"] for r in rows if r["professional"] == "Dr. Andrés Pech")
    a = book(client, date=day, time="12:00", professional_id=pech).json()
    assert a["professional"] == "Dr. Andrés Pech"
    b = book(client, date=day, time="12:00").json()  # aún queda la Dra. Rojas a esa hora
    assert b["professional"] == "Dra. Elena Rojas"
    assert book(client, date=day, time="12:00").status_code == 409
    assert book(client, date=day, time="09:00", professional_id=pech).status_code == 409  # fuera de su horario


def test_reservas_concurrentes_no_duplican(client):
    day = next_weekday(3)
    results = []

    def worker(i):
        results.append(book(client, specialty_id=3, date=day, time="10:00", alias=f"Paciente {i}").status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(201) == 1 and results.count(409) == 5
