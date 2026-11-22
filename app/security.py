"""Hash de contraseñas (PBKDF2) y sesiones firmadas con HMAC. Sólo biblioteca estándar."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

def _load_secret() -> str:
    """Clave de firma: variable MEDIBOT_SECRET o archivo local persistente (excluido de git).

    Persistirla evita que reiniciar el servidor cierre todas las sesiones del personal.
    """
    if os.environ.get("MEDIBOT_SECRET"):
        return os.environ["MEDIBOT_SECRET"]
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".medibot_secret")
    try:
        with open(path, encoding="utf-8") as fh:
            value = fh.read().strip()
            if len(value) >= 32:
                return value
    except OSError:
        pass
    value = secrets.token_hex(32)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(value)
    except OSError:
        pass  # sin permisos de escritura: clave efímera
    return value


_SECRET = _load_secret()
SESSION_SECONDS = 8 * 3600


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except ValueError:
        return False


def make_token(username: str, role: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(
        {"u": username, "r": role, "exp": int(time.time()) + SESSION_SECONDS}).encode()).decode()
    sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def sign_value(value: str, ttl: int = 600) -> str:
    """Token firmado de corta duración (p. ej. acceso ya verificado a una cita) sin guardar el PIN."""
    exp = int(time.time()) + ttl
    sig = hmac.new(_SECRET.encode(), f"{value}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{value}|{exp}|{sig}"


def check_value(token: str | None, value: str) -> bool:
    try:
        v, exp, sig = str(token).split("|")
        good = hmac.new(_SECRET.encode(), f"{v}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return v == value and int(exp) > time.time() and hmac.compare_digest(sig, good)
    except ValueError:
        return False


def read_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    good = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except ValueError:
        return None
    return data if data.get("exp", 0) > time.time() else None
