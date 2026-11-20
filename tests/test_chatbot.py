import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "MEDIBOT_SESSION_SECRET",
    "clave-temporal-exclusiva-para-pruebas-locales-123456789"
)

import main
from app import database as database_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database_module,
        "DATABASE_PATH",
        tmp_path / "medibot_pruebas.db"
    )

    with TestClient(main.app) as api:
        yield api


def available_schedule():
    with database_module.get_db() as db:
        slot = db.execute("""
            SELECT id, professional_id, appointment_date
            FROM schedules
            WHERE status = 'available'
            ORDER BY appointment_date, start_time
            LIMIT 1
        """).fetchone()

    assert slot is not None, "No se generaron horarios de prueba."
    return dict(slot)


def make_chat_booking(client):
    slot = available_schedule()
    response = client.post(
        "/api/appointments",
        json={
            "schedule_id": slot["id"],
            "full_name": "Cliente Ficticio Prueba",
            "email": "pruebas-chatbot@example.com",
            "phone": "9811234567",
            "source": "chatbot"
        }
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result.get("folio", "").startswith("MB-")
    return slot, result


def proof(folio, **changes):
    data = {
        "folio": folio,
        "email": "pruebas-chatbot@example.com",
        "phone": "9811234567"
    }
    data.update(changes)
    return data


def test_01_chatbot_visible_and_static_files(client):
    home = client.get("/")
    assert home.status_code == 200
    assert 'id="mb-chat-toggle"' in home.text
    assert 'id="mb-chat-panel"' in home.text
    assert client.get("/static/js/chatbot.js").status_code == 200
    assert client.get("/static/css/chatbot.css").status_code == 200


def test_02_chat_responses(client):
    hello = client.post("/api/chat", json={"message": "Hola"})
    assert hello.status_code == 200, hello.text
    assert hello.json().get("reply")
    assert hello.json().get("options")

    with database_module.get_db() as db:
        db.execute("""
            UPDATE specialties
            SET price = 925.00
            WHERE name = 'Cardiología'
        """)

    price = client.post(
        "/api/chat",
        json={"message": "¿Cuánto cuesta Cardiología?"}
    )
    assert price.status_code == 200, price.text
    assert "925.00" in price.json()["reply"]

    emergency = client.post(
        "/api/chat",
        json={"message": "Tengo dolor de pecho"}
    )
    assert emergency.status_code == 200, emergency.text
    assert "911" in emergency.json()["reply"]


def test_03_booking_lookup_cancel_crm(client):
    slot, booking = make_chat_booking(client)
    appointment_id = booking["appointment_id"]

    with database_module.get_db() as db:
        schedule = db.execute("""
            SELECT status
            FROM schedules
            WHERE id = ?
        """, (slot["id"],)).fetchone()

        interaction = db.execute("""
            SELECT channel
            FROM interactions
            WHERE customer_id = (
                SELECT customer_id
                FROM appointments
                WHERE id = ?
            )
            ORDER BY id DESC
            LIMIT 1
        """, (appointment_id,)).fetchone()

    assert schedule["status"] == "reserved"
    assert interaction["channel"] == "chatbot"

    duplicate = client.post(
        "/api/appointments",
        json={
            "schedule_id": slot["id"],
            "full_name": "Otro Cliente Ficticio",
            "email": "otro-ejemplo@example.com",
            "phone": "9810000000",
            "source": "chatbot"
        }
    )
    assert duplicate.status_code == 409

    lookup = client.post(
        "/api/chat/appointments/lookup",
        json=proof(booking["folio"])
    )
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["data"]["folio"] == booking["folio"]

    invalid = client.post(
        "/api/chat/appointments/lookup",
        json=proof(booking["folio"], phone="9819999999")
    )
    assert invalid.status_code == 404

    cancel = client.post(
        "/api/chat/appointments/cancel",
        json=proof(booking["folio"])
    )
    assert cancel.status_code == 200, cancel.text

    with database_module.get_db() as db:
        appointment = db.execute("""
            SELECT status
            FROM appointments
            WHERE id = ?
        """, (appointment_id,)).fetchone()
        schedule = db.execute("""
            SELECT status
            FROM schedules
            WHERE id = ?
        """, (slot["id"],)).fetchone()
        last_interaction = db.execute("""
            SELECT channel
            FROM interactions
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

    assert appointment["status"] == "cancelled"
    assert schedule["status"] == "available"
    assert last_interaction["channel"] == "chatbot"

    again = client.post(
        "/api/chat/appointments/cancel",
        json=proof(booking["folio"])
    )
    assert again.status_code == 409


def test_04_paid_appointment_cannot_cancel(client):
    slot, booking = make_chat_booking(client)

    with database_module.get_db() as db:
        amount = db.execute("""
            SELECT agreed_price
            FROM appointments
            WHERE id = ?
        """, (booking["appointment_id"],)).fetchone()["agreed_price"]

        db.execute("""
            INSERT INTO payments
            (appointment_id, amount, status, payment_date)
            VALUES (?, ?, 'paid', CURRENT_TIMESTAMP)
        """, (booking["appointment_id"], amount))

    response = client.post(
        "/api/chat/appointments/cancel",
        json=proof(booking["folio"])
    )
    assert response.status_code == 409, response.text

    with database_module.get_db() as db:
        appointment = db.execute("""
            SELECT status
            FROM appointments
            WHERE id = ?
        """, (booking["appointment_id"],)).fetchone()
        schedule = db.execute("""
            SELECT status
            FROM schedules
            WHERE id = ?
        """, (slot["id"],)).fetchone()

    assert appointment["status"] == "confirmed"
    assert schedule["status"] == "reserved"


def test_05_closed_days_cannot_be_booked(client):
    slot = available_schedule()

    with database_module.get_db() as db:
        db.execute("""
            INSERT INTO schedule_day_settings
            (professional_id, appointment_date, is_closed)
            VALUES (?, ?, 1)
        """, (
            slot["professional_id"],
            slot["appointment_date"]
        ))

    options = client.get(
        "/api/schedules",
        params={
            "professional_id": slot["professional_id"],
            "appointment_date": slot["appointment_date"]
        }
    )
    assert options.status_code == 200, options.text
    assert options.json()["data"] == []

    attempted = client.post(
        "/api/appointments",
        json={
            "schedule_id": slot["id"],
            "full_name": "Reserva No Permitida",
            "email": "cerrado@example.com",
            "phone": "9811234567",
            "source": "chatbot"
        }
    )
    assert attempted.status_code == 409, attempted.text
