from conftest import next_weekday


def test_next_available(client):
    rows = client.get("/api/next-available").json()
    assert len(rows) == 6 and all(r["date"] and r["time"] for r in rows)


def test_ics_requiere_pin(client):
    a = client.post("/api/appointments", json={"specialty_id": 3, "date": next_weekday(2), "time": "12:00",
                                               "alias": "Ics Demo"}).json()
    r = client.get(f"/api/appointments/{a['code']}/ics", params={"pin": a["pin"]})
    assert r.status_code == 200 and "BEGIN:VCALENDAR" in r.text and a["code"] in r.text
    assert client.get(f"/api/appointments/{a['code']}/ics", params={"pin": "111111"}).status_code == 404


def test_busqueda_global_y_actividad(admin):
    a = admin.post("/api/admin/appointments", json={"specialty_id": 2, "date": next_weekday(2), "time": "11:00",
                                                    "alias": "Búsqueda Demo", "phone": "9817776655"}).json()
    assert len(a["pin"]) == 6  # recepción puede entregar el PIN al paciente presencial
    res = admin.get("/api/admin/search", params={"q": "Búsqueda"}).json()
    assert res["customers"][0]["alias"] == "Búsqueda Demo" and res["appointments"][0]["code"] == a["code"]
    assert admin.get("/api/admin/search", params={"q": "7776655"}).json()["customers"]
    assert admin.get("/api/admin/search", params={"q": "a"}).json() == {"customers": [], "appointments": [], "invoices": []}
    act = admin.get("/api/admin/activity").json()
    assert act[0]["kind"] == "cita" and act[0]["who"] == "Búsqueda Demo"


def test_cita_en_recepcion_y_rango(admin):
    day = next_weekday(1)
    r = admin.post("/api/admin/appointments", json={"specialty_id": 1, "date": day, "time": "13:00",
                                                    "alias": "Presencial"})
    assert r.status_code == 201
    rows = admin.get("/api/admin/appointments", params={"start": day, "end": day}).json()
    assert any(a["channel"] == "recepcion" for a in rows)
    assert admin.get("/api/admin/appointments", params={"q": r.json()["code"]}).json()[0]["alias"] == "Presencial"


def test_exportacion_csv_y_proteccion_formulas(admin):
    admin.post("/api/admin/customers", json={"alias": "=HYPERLINK(1)"})
    r = admin.get("/api/admin/export/pacientes.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK(1)" in r.text
    assert admin.get("/api/admin/export/nada.csv").status_code == 404


def test_seed_demo_genera_actividad(admin):
    from scripts import seed_demo
    seed_demo.main(force=True)
    d = admin.get("/api/admin/dashboard").json()
    assert d["customers"] >= 20 and d["income"] > 0 and d["chats"] >= 180
    rep = admin.get("/api/admin/reports").json()
    assert rep["income_by_day"] and rep["appointments_by_day"]


def test_exportacion_requiere_sesion(client):
    assert client.get("/api/admin/export/pacientes.csv").status_code == 401
    assert client.post("/api/admin/appointments", json={}).status_code in (401, 422)
