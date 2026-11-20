# =====================================================
# MEDIBOT 360 - ETAPA 12
# PRUEBAS DE CHATBOT AMPLIADO, CRM (PROSPECTOS) Y ERP (REPORTES)
# =====================================================

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "MEDIBOT_SESSION_SECRET",
    "clave-local-de-pruebas-123456789-abcdef"
)

import main
from app import database as database_module
from app.security import hash_password

SAME_ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database_module,
        "DATABASE_PATH",
        tmp_path / "modules_test.db"
    )

    with TestClient(main.app) as api:
        yield api


def login(client):
    with database_module.get_db() as db:
        db.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, 'admin')
        """, ("admin_modulos", hash_password("ClaveFicticiaSegura2026!")))

    response = client.post(
        "/api/auth/login",
        json={
            "username": "admin_modulos",
            "password": "ClaveFicticiaSegura2026!"
        },
        headers=SAME_ORIGIN
    )
    assert response.status_code == 200, response.text


def chat(client, text):
    response = client.post("/api/chat", json={"message": text})
    assert response.status_code == 200, response.text
    return response.json()


def first_slot():
    with database_module.get_db() as db:
        return dict(db.execute("""
            SELECT id FROM schedules
            WHERE status = 'available'
            ORDER BY appointment_date, start_time
            LIMIT 1
        """).fetchone())


CONTACT = {
    "full_name": "Prospecto Ficticio",
    "email": "Prospecto@Example.com",
    "phone": "9811112233",
    "message": "Quisiera información sobre nutrición."
}


# ---------------------- CHATBOT ----------------------

def test_chat_new_intents(client):
    assert chat(client, "¿Dónde están ubicados?")["intent"] == "contacto"
    assert "Campeche" in chat(client, "ubicación")["reply"]
    assert chat(client, "Muchas gracias")["intent"] == "despedida"

    team = chat(client, "¿Qué doctores tienen en Cardiología?")
    assert team["intent"] == "equipo"
    assert "Dr. Daniel Vega" in team["reply"]
    assert "Elena Rojas" not in team["reply"]

    assert chat(client, "asdfgh")["intent"] == "no_entendido"
    assert chat(client, "Tengo dolor de pecho")["intent"] == "emergencia"


def test_chat_schedules_come_from_database(client):
    answer = chat(client, "¿Qué horarios hay de Cardiología?")
    assert answer["intent"] == "horarios"
    assert "Próximos turnos libres de Cardiología" in answer["reply"]
    assert "Dr. Daniel Vega" in answer["reply"]
    assert "Elena Rojas" not in answer["reply"]

    with database_module.get_db() as db:
        db.execute("UPDATE schedules SET status = 'blocked'")

    empty = chat(client, "horarios disponibles")
    assert "No encontré turnos libres" in empty["reply"]


def test_chat_messages_are_logged_for_crm(client):
    chat(client, "Hola")
    chat(client, "precios")

    with database_module.get_db() as db:
        rows = db.execute("""
            SELECT intent, customer_id FROM interactions
            WHERE channel = 'chatbot' ORDER BY id
        """).fetchall()

    assert [r["intent"] for r in rows] == ["saludo", "precios"]
    assert all(r["customer_id"] is None for r in rows)


# ---------------------- CRM ----------------------

def test_contact_form_creates_lead_without_duplicates(client):
    first = client.post("/api/contact", json=CONTACT)
    assert first.status_code == 201, first.text

    again = client.post("/api/contact", json=CONTACT)
    assert again.status_code == 201

    with database_module.get_db() as db:
        customers = db.execute("""
            SELECT email, status, source FROM customers
        """).fetchall()
        interactions = db.execute("""
            SELECT COUNT(*) AS n FROM interactions
            WHERE channel = 'contacto'
        """).fetchone()["n"]

    assert len(customers) == 1
    assert customers[0]["email"] == "prospecto@example.com"
    assert customers[0]["status"] == "lead"
    assert customers[0]["source"] == "contacto"
    assert interactions == 2


def test_contact_form_validation_and_rate_limit(client):
    bad_email = client.post("/api/contact", json={**CONTACT, "email": "no-es-correo"})
    assert bad_email.status_code == 400

    short = client.post("/api/contact", json={**CONTACT, "message": "hi"})
    assert short.status_code == 422

    # 1 intento inválido (400) ya contó; 4 más llegan al límite de 5.
    codes = [
        client.post("/api/contact", json={**CONTACT, "email": f"x{i}@example.com"}).status_code
        for i in range(5)
    ]
    assert codes[-1] == 429


def test_lead_becomes_active_when_booking(client):
    client.post("/api/contact", json=CONTACT)

    booking = client.post(
        "/api/appointments",
        json={
            "schedule_id": first_slot()["id"],
            "full_name": "Prospecto Ficticio",
            "email": "prospecto@example.com",
            "phone": "9811112233",
            "source": "web"
        }
    )
    assert booking.status_code == 200, booking.text

    with database_module.get_db() as db:
        status = db.execute(
            "SELECT status FROM customers WHERE email = ?",
            ("prospecto@example.com",)
        ).fetchone()["status"]

    assert status == "active"


def test_customer_filters_and_new_source(client):
    login(client)
    client.post("/api/contact", json=CONTACT)
    client.post(
        "/api/appointments",
        json={
            "schedule_id": first_slot()["id"],
            "full_name": "Cliente Del Chatbot",
            "email": "chatbot@example.com",
            "phone": "9810000000",
            "source": "chatbot"
        }
    )

    leads = client.get("/api/admin/customers?status=lead").json()["data"]
    assert [c["email"] for c in leads] == ["prospecto@example.com"]

    from_chatbot = client.get("/api/admin/customers?source=chatbot").json()["data"]
    assert [c["email"] for c in from_chatbot] == ["chatbot@example.com"]

    assert client.get("/api/admin/customers?status=otro").status_code == 400
    assert client.get("/api/admin/customers?source=otro").status_code == 400

    profile = client.put(
        f"/api/admin/customers/{leads[0]['id']}",
        json={
            "full_name": "Prospecto Ficticio",
            "email": "prospecto@example.com",
            "phone": "9811112233",
            "status": "lead"
        },
        headers=SAME_ORIGIN
    )
    assert profile.status_code == 200, profile.text


# ---------------------- ERP: EXPORTACIÓN Y REPORTES ----------------------

def test_exports_and_reports_require_session(client):
    for url in (
        "/api/admin/export/customers.csv",
        "/api/admin/export/appointments.csv",
        "/api/admin/reports?days=30"
    ):
        assert client.get(url).status_code == 401

    assert client.get("/admin/reportes", follow_redirects=False).status_code == 303


def test_csv_exports_and_formula_protection(client):
    login(client)
    client.post("/api/contact", json={**CONTACT, "full_name": "=HYPERLINK(\"x\")"})

    response = client.get("/api/admin/export/customers.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "Prospecto" in response.text
    assert "'=HYPERLINK" in response.text

    for kind in ("appointments", "finance", "inventory"):
        ok = client.get(f"/api/admin/export/{kind}.csv")
        assert ok.status_code == 200, kind
        assert ok.text.startswith("﻿")

    assert client.get("/api/admin/export/secretos.csv").status_code == 404


def test_reports_aggregate_all_modules(client):
    login(client)
    chat(client, "Hola")
    client.post("/api/contact", json=CONTACT)
    client.post(
        "/api/appointments",
        json={
            "schedule_id": first_slot()["id"],
            "full_name": "Cliente Reporte",
            "email": "reporte@example.com",
            "phone": "9810000001",
            "source": "web"
        }
    )

    page = client.get("/admin/reportes")
    assert page.status_code == 200
    assert "report-kpis" in page.text

    report = client.get("/api/admin/reports?days=30")
    assert report.status_code == 200, report.text
    data = report.json()

    assert data["kpis"]["appointments"] == 1
    assert data["kpis"]["confirmed"] == 1
    assert data["kpis"]["new_customers"] == 2
    assert data["kpis"]["chat_messages"] == 1
    assert data["kpis"]["contact_requests"] == 1
    assert data["kpis"]["receivable"] > 0
    assert any(i["intent"] == "saludo" for i in data["chatbot_intents"])
    assert len(data["specialties"]) == 6
    assert {s["source"] for s in data["customers_by_source"]} == {"web", "contacto"}

    assert client.get("/api/admin/reports?days=15").status_code == 400
