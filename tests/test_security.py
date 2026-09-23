import pytest

from app.core.security import create_access_token, create_refresh_token


def test_x_user_id_header_is_not_an_identity(client):
    assert client.get("/api/v1/admin/overview", headers={"X-User-Id": "1"}).status_code == 401
    bad = {"Authorization": "Bearer garbage", "X-User-Id": "1"}
    assert client.get("/api/v1/admin/overview", headers=bad).status_code == 401


def test_no_token_is_never_a_fallback_user(client):
    assert client.get("/api/v1/admin/overview").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    headers = {"Authorization": f"Bearer {create_refresh_token(1)}"}
    assert client.get("/api/v1/admin/overview", headers=headers).status_code == 401
    ok = {"Authorization": f"Bearer {create_access_token(1)}"}
    assert client.get("/api/v1/admin/overview", headers=ok).status_code == 200


def test_cannot_self_register_as_admin(client):
    payload = {
        "email": "sneaky@example.com",
        "password": "secret123",
        "username": "sneaky",
        "first_name": "Sneaky",
        "last_name": "User",
        "mobile_no": "9000000099",
        "role": "admin",
        "dob": "1999-01-01",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422
    payload["role"] = "influencer"
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    assert resp.json()["role"] == "influencer"


def test_otp_is_voided_after_too_many_wrong_guesses(client, db_session, monkeypatch):
    # Never send a real e-mail from the test suite; capture the OTP it would have sent.
    sent = {}
    monkeypatch.setattr(
        "app.common.services.auth_service.send_otp_email",
        lambda to, otp: sent.__setitem__("otp", otp),
    )
    from app.common.models.user import User
    from app.common.services.auth_service import AuthService, MAX_OTP_ATTEMPTS

    user = db_session.query(User).filter(User.email == "priya@talktamila.com").first()
    AuthService.create_otp(db_session, user.email)
    real_otp = sent["otp"]
    wrong = "000000" if real_otp != "000000" else "111111"

    for _ in range(MAX_OTP_ATTEMPTS):
        resp = client.post("/api/v1/auth/verify-otp", json={"identifier": user.email, "otp": wrong})
        assert resp.status_code == 400

    # Even the correct code no longer works: a fresh OTP has to be requested.
    resp = client.post("/api/v1/auth/verify-otp", json={"identifier": user.email, "otp": real_otp})
    assert resp.status_code == 400


def test_signup_requires_last_name_dob_and_mobile(client):
    base = {
        "email": "strict@example.com",
        "password": "secret123",
        "username": "strictuser",
        "first_name": "Strict",
        "last_name": "User",
        "mobile_no": "9000000123",
        "dob": "1999-01-01",
        "role": "influencer",
    }
    for missing in ("last_name", "dob", "mobile_no", "username"):
        payload = {k: v for k, v in base.items() if k != missing}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 422, missing

    assert client.post("/api/v1/auth/register", json={**base, "last_name": "   "}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "mobile_no": "12345"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "dob": "2999-01-01"}).status_code == 422

    assert client.post("/api/v1/auth/register", json=base).status_code == 201


def test_signup_still_accepts_full_name_only(client):
    payload = {
        "email": "fullname@example.com",
        "password": "secret123",
        "username": "fullnameuser",
        "full_name": "Asha Kumar",
        "mobile_no": "9000000124",
        "dob": "1999-01-01",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    assert resp.json()["full_name"] == "Asha Kumar"
    # a single word is not enough: last name is required
    resp = client.post("/api/v1/auth/register", json={**payload, "email": "one@example.com", "username": "oneword", "mobile_no": "9000000125", "full_name": "Asha"})
    assert resp.status_code == 422


def test_verified_otp_can_still_reset_after_a_few_wrong_guesses(client, db_session, monkeypatch):
    # Regression: reset-password used to re-spend attempts on an OTP that
    # verify_otp had already confirmed, which could void a good code.
    sent = {}
    monkeypatch.setattr(
        "app.common.services.auth_service.send_otp_email",
        lambda to, otp: sent.__setitem__("otp", otp),
    )
    email = "verifiedreset@example.com"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "secret123", "username": "verifiedreset",
        "first_name": "V", "last_name": "R", "mobile_no": "9000000200", "dob": "1999-01-01",
    })
    assert client.post("/api/v1/auth/forgot-password", json={"identifier": email}).status_code == 200
    otp = sent["otp"]

    # Three wrong guesses at /verify-otp (below the 5-attempt limit).
    for _ in range(3):
        assert client.post("/api/v1/auth/verify-otp", json={"identifier": email, "otp": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/verify-otp", json={"identifier": email, "otp": otp}).status_code == 200

    resp = client.post("/api/v1/auth/reset-password", json={"identifier": email, "otp": otp, "new_password": "brandnew123"})
    assert resp.status_code == 200

    assert client.post("/api/v1/auth/login", json={"username": "verifiedreset", "password": "brandnew123"}).status_code == 200


def test_cors_rejects_arbitrary_origins(client):
    # Regression: CORS used to accept any http(s) origin (allow_origin_regex=".*"),
    # a severe risk once combined with allow_credentials=True.
    resp = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil-phishing-site.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}


def test_secret_key_rejects_known_default_in_production(monkeypatch):
    # Regression: SECRET_KEY silently fell back to a hardcoded value if unset.
    import importlib
    monkeypatch.setenv("SECRET_KEY", "dev_secret_key_change_in_production_jwt_9348572849")
    monkeypatch.setenv("ENVIRONMENT", "production")
    import app.core.config as config_module
    try:
        with pytest.raises(Exception):
            importlib.reload(config_module)
    finally:
        monkeypatch.setenv("SECRET_KEY", "x" * 64)
        monkeypatch.setenv("ENVIRONMENT", "development")
        importlib.reload(config_module)


def test_expired_story_not_reachable_by_direct_id(client, db_session, creator_auth_headers):
    from datetime import datetime, timedelta
    from app.common.models import Story

    payload = {
        "media_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "media_type": "image",
        "caption": "expiring soon",
        "duration_hours": 24,
    }
    resp = client.post("/api/stories", json=payload, headers=creator_auth_headers)
    assert resp.status_code == 201
    story_id = resp.json()["id"]

    story = db_session.get(Story, story_id)
    story.expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()

    resp = client.get(f"/api/stories/{story_id}", headers=creator_auth_headers)
    assert resp.status_code == 404


def test_otp_is_hashed_at_rest(db_session, monkeypatch):
    # Regression: reset_otp used to store the raw 6-digit code; a DB leak
    # would have exposed every pending reset code as-is.
    sent = {}
    monkeypatch.setattr(
        "app.common.services.auth_service.send_otp_email",
        lambda to, otp: sent.__setitem__("otp", otp),
    )
    from app.common.models.user import User
    from app.common.services.auth_service import AuthService

    user = db_session.query(User).filter(User.email == "priya@talktamila.com").first()
    AuthService.create_otp(db_session, user.email)
    db_session.refresh(user)

    assert user.reset_otp != sent["otp"]
    assert len(user.reset_otp) == 64  # sha256 hex digest, not the 6-digit code