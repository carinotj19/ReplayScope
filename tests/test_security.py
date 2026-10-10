"""Security regression tests: API authorization, CSRF, cookies and safe headers."""
import re

import pytest
from werkzeug.security import generate_password_hash

from replayscope import create_app
from replayscope.models import db

PASSWORD = "a-demo-password-that-is-not-a-production-secret"


@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True, "AUTH_ENABLED": True,
        "SECRET_KEY": "s" * 48,
        "ADMIN_PASSWORD_HASH": generate_password_hash(PASSWORD),
        "API_TOKEN": "t" * 48,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "auth.sqlite3"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    })
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.drop_all()


def csrf(c):
    response = c.get("/login")
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match
    return match.group(1).decode()


def sign_in(c):
    token = csrf(c)
    response = c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    assert response.status_code == 303
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    with c.session_transaction() as sess:
        assert sess["authenticated"]
        return sess["_csrf"]


def test_requires_login_for_dashboard_and_api(client):
    assert client.get("/").status_code == 302
    assert client.get("/experiments/1").status_code == 302
    assert client.get("/api/v1/experiments").status_code == 401
    assert client.post("/api/v1/experiments", json={"name": "No"}).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_login_requires_csrf_and_correct_password(client):
    assert client.post("/login", data={"password": PASSWORD}).status_code == 403
    token = csrf(client)
    assert client.post("/login", data={"password": "wrong", "csrf_token": token}).status_code == 401
    sign_in(client)
    assert client.get("/").status_code == 200


def test_session_writes_require_csrf(client):
    token = sign_in(client)
    assert client.get("/api/v1/experiments").status_code == 200
    assert client.post("/api/v1/experiments", json={"name": "No CSRF"}).status_code == 403
    assert client.post("/api/v1/experiments", json={"name": "Invalid"},
                       headers={"X-CSRF-Token": "no"}).status_code == 403
    ok = client.post("/api/v1/experiments", json={"name": "Allowed"},
                     headers={"X-CSRF-Token": token})
    assert ok.status_code == 201
    assert client.post("/logout").status_code == 403
    assert client.post("/logout", data={"csrf_token": token}).status_code == 303
    assert client.get("/api/v1/experiments").status_code == 401


def test_valid_bearer_for_api_only(client):
    h = {"Authorization": "Bearer " + "t" * 48}
    assert client.get("/api/v1/experiments", headers=h).status_code == 200
    assert client.post("/api/v1/experiments", json={"name": "Automated"},
                       headers=h).status_code == 201
    assert client.get("/", headers=h).status_code == 401
    assert client.get("/api/v1/experiments",
                      headers={"Authorization": "Bearer bad"}).status_code == 401


def test_defensive_headers(client):
    response = client.get("/login")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_auth_config_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="SECRET_KEY and ADMIN_PASSWORD_HASH"):
        create_app({"AUTH_ENABLED": True, "TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "bad.db")})
    with pytest.raises(ValueError, match="at least 32"):
        create_app({"AUTH_ENABLED": True, "TESTING": True,
                    "SECRET_KEY": "short",
                    "ADMIN_PASSWORD_HASH": generate_password_hash(PASSWORD),
                    "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "bad2.db")})


def test_login_rate_limit(client):
    token = csrf(client)
    for _ in range(5):
        response = client.post("/login", data={
            "password": "incorrect", "csrf_token": token,
        }, environ_base={"REMOTE_ADDR": "198.51.100.77"})
        assert response.status_code == 401
    result = client.post("/login", data={
        "password": PASSWORD, "csrf_token": token,
    }, environ_base={"REMOTE_ADDR": "198.51.100.77"})
    assert result.status_code == 429


def test_browser_upload_with_csrf(client):
    import io
    import json

    token = sign_in(client)
    result = client.post("/api/v1/experiments", json={"name": "Secure ingestion"},
                         headers={"X-CSRF-Token": token})
    assert result.status_code == 201
    runs = {"runs": [{
        "agent": "SecuredBot", "version": "1", "scenario": "sample",
        "outcome": "success", "score": 1,
    }]}
    multipart = {
        "experiment_id": str(result.json["id"]),
        "file": (io.BytesIO(json.dumps(runs).encode()), "test.json"),
    }
    assert client.post("/api/v1/uploads", data=multipart).status_code == 403
    multipart["file"] = (io.BytesIO(json.dumps(runs).encode()), "test.json")
    authorized = client.post("/api/v1/uploads", data=multipart,
                             headers={"X-CSRF-Token": token})
    assert authorized.status_code == 201
    assert authorized.json["status"] == "ready"
