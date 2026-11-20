# =====================================================
# MEDIBOT 360 - ETAPA 10B
# PRUEBAS AUTOMATICAS DE SEGURIDAD
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

SAME_ORIGIN = {
    "Origin": "http://testserver"
}

BAD_ORIGIN = {
    "Origin": "https://sitio-externo.example"
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_database = tmp_path / "security_test.db"
    monkeypatch.setattr(
        database_module,
        "DATABASE_PATH",
        test_database
    )

    with TestClient(main.app) as test_client:
        yield test_client


def login_test_admin(client):
    with database_module.get_db() as db:
        db.execute("""
            INSERT INTO users
                (username, password_hash, role)
            VALUES (?, ?, 'admin')
        """, (
            "admin_seguridad",
            hash_password("ClaveFicticiaSegura2026!")
        ))

    response = client.post(
        "/api/auth/login",
        json={
            "username": "admin_seguridad",
            "password": "ClaveFicticiaSegura2026!"
        },
        headers=SAME_ORIGIN
    )
    assert response.status_code == 200, response.text
    return response


def test_admin_requires_session(client):
    response = client.get("/api/admin/customers")
    assert response.status_code == 401


def test_login_uses_protected_cookie(client):
    response = login_test_admin(client)
    cookie = response.headers.get("set-cookie", "").lower()
    assert "medibot_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_cross_site_admin_request_is_rejected(client):
    login_test_admin(client)

    payload = {
        "name": "Recurso de Seguridad",
        "description": "Prueba ficticia",
        "quantity": 2,
        "status": "available"
    }

    response = client.post(
        "/api/admin/resources",
        json=payload,
        headers=BAD_ORIGIN
    )
    assert response.status_code == 403

    correct = client.post(
        "/api/admin/resources",
        json=payload,
        headers=SAME_ORIGIN
    )
    assert correct.status_code == 201, correct.text


def test_missing_origin_is_rejected(client):
    login_test_admin(client)

    response = client.post(
        "/api/admin/resources",
        json={
            "name": "Recurso No Permitido",
            "description": "Prueba",
            "quantity": 1,
            "status": "available"
        }
    )
    assert response.status_code == 403


def test_login_rate_limit(client):
    for _ in range(10):
        response = client.post(
            "/api/auth/login",
            json={
                "username": "usuario_inexistente",
                "password": "incorrecta"
            },
            headers=SAME_ORIGIN
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/auth/login",
        json={
            "username": "usuario_inexistente",
            "password": "incorrecta"
        },
        headers=SAME_ORIGIN
    )
    assert blocked.status_code == 429


def test_chat_folio_rate_limit(client):
    payload = {
        "folio": "MB-ABCDEF12",
        "email": "incorrecto@example.com",
        "phone": "9811234567"
    }

    for _ in range(8):
        response = client.post(
            "/api/chat/appointments/lookup",
            json=payload
        )
        assert response.status_code == 404

    blocked = client.post(
        "/api/chat/appointments/lookup",
        json=payload
    )
    assert blocked.status_code == 429


def test_logout_invalidates_session(client):
    login_test_admin(client)

    before = client.get("/api/admin/customers")
    assert before.status_code == 200

    logout = client.post(
        "/api/auth/logout",
        headers=SAME_ORIGIN
    )
    assert logout.status_code == 200

    after = client.get("/api/admin/customers")
    assert after.status_code == 401


def test_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"

    private = client.get("/api/admin/customers")
    assert private.headers.get("cache-control") == "no-store"
