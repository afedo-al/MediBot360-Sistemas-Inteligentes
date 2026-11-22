from conftest import next_weekday


def test_admin_requiere_login_y_roles(client):
    assert client.get("/api/admin/customers").status_code == 401
    assert client.post("/api/admin/login", json={"username": "admin", "password": "mala"}).status_code == 401
    client.post("/api/admin/login", json={"username": "recepcion", "password": "Recep#test1"})
    assert client.get("/api/admin/customers").status_code == 200
    assert client.get("/api/admin/audit").status_code == 403
    r = client.post("/api/admin/specialties", json={"name": "Oftalmología", "price": 700})
    assert r.status_code == 403


def test_bloqueo_por_intentos(client):
    for _ in range(5):
        client.post("/api/admin/login", json={"username": "admin", "password": "x"})
    r = client.post("/api/admin/login", json={"username": "admin", "password": "Admin#test1"})
    assert r.status_code == 429


def test_crm_cliente_historial_y_etapas(admin):
    r = admin.post("/api/admin/customers", json={"alias": "Prospecto Uno", "phone": "9811112222"})
    cid = r.json()["id"]
    assert admin.patch(f"/api/admin/customers/{cid}", json={"stage": "contactado"}).status_code == 200
    admin.post(f"/api/admin/customers/{cid}/interactions", json={"kind": "llamada", "note": "Se llamó"})
    det = admin.get(f"/api/admin/customers/{cid}").json()
    assert det["stage"] == "contactado" and len(det["interactions"]) == 2
    assert admin.post("/api/admin/customers", json={"alias": "A", "phone": "12"}).status_code == 422
    assert admin.get("/api/admin/pipeline").json()["contactado"] == 1


def test_reserva_convierte_prospecto_en_cliente(admin):
    admin.post("/api/admin/customers", json={"alias": "Ana Demo", "phone": "9815550000"})
    admin.post("/api/appointments", json={"specialty_id": 1, "date": next_weekday(3), "time": "10:00",
                                          "alias": "Ana Demo", "phone": "9815550000"})
    rows = admin.get("/api/admin/customers", params={"q": "9815550000"}).json()
    assert len(rows) == 1 and rows[0]["stage"] == "cliente"


def test_cita_completar_cobrar_y_reportes(admin):
    code = admin.post("/api/appointments", json={"specialty_id": 2, "date": next_weekday(1), "time": "11:00",
                                                 "alias": "Pago Demo"}).json()["code"]
    appt = [a for a in admin.get("/api/admin/appointments").json() if a["code"] == code][0]
    assert admin.post(f"/api/admin/appointments/{appt['id']}/payment", json={"method": "efectivo"}).status_code == 409
    assert admin.post(f"/api/admin/appointments/{appt['id']}/status", json={"status": "completada"}).status_code == 200
    pay = admin.post(f"/api/admin/appointments/{appt['id']}/payment", json={"method": "tarjeta"})
    assert pay.status_code == 201 and pay.json()["amount"] == 850
    assert pay.json()["invoice"].startswith("FAC-")
    assert admin.post(f"/api/admin/appointments/{appt['id']}/payment", json={"method": "tarjeta"}).status_code == 409
    rep = admin.get("/api/admin/reports").json()
    assert rep["income_by_specialty"][0]["value"] == 850
    assert admin.get("/api/admin/dashboard").json()["income"] == 850


def test_erp_catalogo_horarios_e_inventario(admin):
    r = admin.post("/api/admin/specialties", json={"name": "Oftalmología", "price": 700})
    sid = r.json()["id"]
    assert admin.post("/api/admin/specialties", json={"name": "Oftalmología", "price": 1}).status_code == 409
    pid = admin.post("/api/admin/professionals", json={"name": "Dr. Prueba", "specialty_id": sid}).json()["id"]
    assert admin.post("/api/admin/schedules", json={"professional_id": pid, "weekday": 0, "start": "10:00",
                                                    "end": "09:00"}).status_code == 400
    admin.post("/api/admin/schedules", json={"professional_id": pid, "weekday": 0, "start": "10:00", "end": "12:00"})
    inv = admin.get("/api/admin/inventory").json()
    item = inv[0]
    assert admin.post(f"/api/admin/inventory/{item['id']}/movement",
                      json={"delta": -9999, "reason": "prueba"}).status_code == 409
    assert admin.post(f"/api/admin/inventory/{item['id']}/movement",
                      json={"delta": -item["stock"], "reason": "uso"}).status_code == 200
    assert any(i["low"] for i in admin.get("/api/admin/inventory").json())
    assert admin.get("/api/admin/dashboard").json()["low_stock"] >= 1
    assert len(admin.get(f"/api/admin/inventory/{item['id']}/movements").json()) == 1
