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
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422
    payload["role"] = "influencer"
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    assert resp.json()["role"] == "influencer"


def test_otp_is_voided_after_too_many_wrong_guesses(client, db_session, monkeypatch):
    # Never send a real e-mail from the test suite.
    monkeypatch.setattr("app.common.services.auth_service.send_otp_email", lambda *a, **k: None)
    from app.common.models.user import User
    from app.common.services.auth_service import AuthService, MAX_OTP_ATTEMPTS

    user = db_session.query(User).filter(User.email == "priya@talktamila.com").first()
    AuthService.create_otp(db_session, user.email)
    db_session.refresh(user)
    real_otp = user.reset_otp
    wrong = "000000" if real_otp != "000000" else "111111"

    for _ in range(MAX_OTP_ATTEMPTS):
        resp = client.post("/api/v1/auth/verify-otp", json={"identifier": user.email, "otp": wrong})
        assert resp.status_code == 400

    # Even the correct code no longer works: a fresh OTP has to be requested.
    resp = client.post("/api/v1/auth/verify-otp", json={"identifier": user.email, "otp": real_otp})
    assert resp.status_code == 400