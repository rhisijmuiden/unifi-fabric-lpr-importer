import pytest
from fastapi.testclient import TestClient

from app import db as app_db
from app.config import get_settings
from app.services import access_mock, ratelimit
from app.models import User
from app.security import hash_password

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
ADMIN_PASSWORD = "admin-password-123"


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LPR_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("LPR_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LPR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LPR_FRONTEND_DIST", str(tmp_path / "no-dist"))
    monkeypatch.setenv("LPR_ACCESS_MOCK", "empty")
    monkeypatch.setenv("LPR_JOBS_INLINE", "true")
    monkeypatch.setenv("LPR_SCHEDULER", "false")
    get_settings.cache_clear()
    access_mock.reset()
    ratelimit.reset()
    app_db.reset_engine()
    app_db.Base.metadata.create_all(app_db.get_engine())
    yield tmp_path
    app_db.reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def db(app_env):
    session = next(app_db.get_db())
    yield session
    session.close()


@pytest.fixture
def client(app_env, db):
    from app.main import create_app

    db.add(User(username="admin", role="admin", password_hash=hash_password(ADMIN_PASSWORD)))
    db.commit()
    with TestClient(create_app(), headers=HEADERS) as c:
        yield c


@pytest.fixture
def admin_client(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return client
