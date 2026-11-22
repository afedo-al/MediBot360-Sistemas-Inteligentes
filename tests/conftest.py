import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path):
    os.environ["MEDIBOT_DB"] = str(tmp_path / "test.db")
    os.environ["MEDIBOT_ADMIN_PASSWORD"] = "Admin#test1"
    os.environ["MEDIBOT_RECEPCION_PASSWORD"] = "Recep#test1"
    from fastapi.testclient import TestClient
    import main
    from app import services
    main._failures.clear()
    services._attempts.clear()
    with TestClient(main.app) as c:
        yield c


def next_weekday(offset=1):
    d = date.today() + timedelta(days=offset)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.isoformat()


@pytest.fixture()
def admin(client):
    r = client.post("/api/admin/login", json={"username": "admin", "password": "Admin#test1"})
    assert r.status_code == 200
    return client
