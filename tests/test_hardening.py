from fastapi.testclient import TestClient

from app.core import rate_limit as rl
from app.core.config import settings
from app.main import app
from app.utils import admin_bootstrap


def test_every_route_lives_under_api_v1_only():
    paths = list(app.openapi()["paths"])
    assert paths, "no routes found"
    assert all(p.startswith("/api/v1/") or p == "/health" for p in paths)
    assert len(paths) == len(set(paths))


def test_old_duplicate_prefix_is_gone(client: TestClient, admin_auth_headers):
    assert client.get("/api/posts", headers=admin_auth_headers).status_code == 404


def test_removed_endpoints_are_gone(client: TestClient, admin_auth_headers):
    for method, path in (
        ("post", "/api/v1/auth/register"),
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/stories/mutes"),
        ("get", "/api/v1/superadmin/health"),
        ("get", "/api/v1/freelancer/health"),
    ):
        assert getattr(client, method)(path, headers=admin_auth_headers).status_code in (404, 405), path


def test_health_reveals_nothing(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_forgot_password_does_not_reveal_accounts(client: TestClient):
    r = client.post("/api/v1/auth/forgot-password", json={"identifier": "nobody-here@example.com"})
    assert r.status_code == 200


def test_login_is_rate_limited(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    rl.reset_rate_limits()
    codes = [
        client.post("/api/v1/auth/login", json={"username": "x", "password": "wrong-password"}).status_code
        for _ in range(12)
    ]
    rl.reset_rate_limits()
    assert 429 in codes and codes[0] == 401


def test_no_default_admin_password_in_production(db_session, monkeypatch):
    from app.common.models import User

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_PASSWORD", "")
    monkeypatch.setattr(admin_bootstrap, "ADMIN_USERNAME", "brand_new_admin")
    monkeypatch.setattr(admin_bootstrap, "ADMIN_EMAIL", "brand_new_admin@example.com")
    admin_bootstrap.ensure_admin_user(db_session)
    assert db_session.query(User).filter(User.username == "brand_new_admin").first() is None


def test_refresh_blocked_for_suspended_user(client: TestClient, db_session):
    from app.common.models import User
    from app.core.security import create_refresh_token

    user = db_session.query(User).filter(User.role == "influencer").first()
    token = create_refresh_token(user.user_id)
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 200
    user.is_active = False
    db_session.commit()
    try:
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401
    finally:
        user.is_active = True
        db_session.commit()


def test_scheduler_cycle_never_raises():
    from app.core.scheduler import run_publish_cycle

    def broken_factory():
        raise RuntimeError("db down")

    # A failing database must not kill the background loop.
    assert run_publish_cycle(broken_factory) == 0