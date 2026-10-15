"""Endpoints whose logic lives in a service (profile, notifications, settings, auth, posts).

These guard the route -> service wiring: if a handler and its service method drift
apart, one of these fails.
"""

from fastapi.testclient import TestClient

from app.common.models.social import Notification


# ------------------------------------------------------------------ auth
def test_check_availability_reports_taken_and_free_values(client: TestClient):
    response = client.get(
        "/api/v1/auth/check-availability",
        params={"email": "nobody-uses-this@example.com", "username": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"]["available"] is True
    assert body["username"]["available"] is False
    assert body["username"]["message"]


def test_refresh_returns_new_tokens_and_rejects_access_token(client: TestClient, db_session):
    from app.core.security import create_access_token, create_refresh_token

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": create_refresh_token(2)})
    assert refreshed.status_code == 200
    assert refreshed.json()["token_type"] == "bearer"

    wrong_type = client.post("/api/v1/auth/refresh", json={"refresh_token": create_access_token(2)})
    assert wrong_type.status_code == 401


def test_change_password_needs_login(client: TestClient):
    response = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "x", "new_password": "123456", "otp": "123456"},
    )
    assert response.status_code == 401


# --------------------------------------------------------------- my profile
def test_get_my_profile_includes_follow_counts(client: TestClient, creator_auth_headers):
    response = client.get("/api/v1/auth/profile", headers=creator_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == 2
    assert isinstance(body["followers_count"], int)
    assert isinstance(body["following_count"], int)


def test_update_my_profile_rejects_taken_username(client: TestClient, creator_auth_headers):
    response = client.put(
        "/api/v1/auth/profile",
        data={"first_name": "Creator", "username": "admin"},
        headers=creator_auth_headers,
    )
    assert response.status_code == 400


# ------------------------------------------------------------ notifications
def test_notification_counts_mark_read_and_delete(client: TestClient, db_session, creator_auth_headers):
    db_session.add_all(
        [
            Notification(user_id=2, type="follow", message="a", is_read=False),
            Notification(user_id=2, type="follow", message="b", is_read=False),
        ]
    )
    db_session.commit()

    before = client.get("/api/v1/notifications/unread-count", headers=creator_auth_headers).json()["unread_count"]
    assert before >= 2

    first_id = (
        db_session.query(Notification)
        .filter(Notification.user_id == 2, Notification.is_read.is_(False))
        .first()
        .id
    )
    assert client.post(f"/api/v1/notifications/{first_id}/read", headers=creator_auth_headers).status_code == 200
    after_one = client.get("/api/v1/notifications/unread-count", headers=creator_auth_headers).json()["unread_count"]
    assert after_one == before - 1

    assert client.post("/api/v1/notifications/read-all", headers=creator_auth_headers).status_code == 200
    assert client.get("/api/v1/notifications/unread-count", headers=creator_auth_headers).json()["unread_count"] == 0

    assert client.delete(f"/api/v1/notifications/{first_id}", headers=creator_auth_headers).status_code == 200
    assert client.delete(f"/api/v1/notifications/{first_id}", headers=creator_auth_headers).status_code == 404


def test_cannot_touch_another_users_notification(client: TestClient, db_session, creator_auth_headers, influencer_auth_headers):
    note = Notification(user_id=3, type="follow", message="private", is_read=False)
    db_session.add(note)
    db_session.commit()
    response = client.post(f"/api/v1/notifications/{note.id}/read", headers=creator_auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------- story settings
def test_followers_and_following_lists(client: TestClient, creator_auth_headers):
    assert client.get("/api/v1/stories/settings/followers/2", headers=creator_auth_headers).status_code == 200
    assert client.get("/api/v1/stories/settings/following/2", headers=creator_auth_headers).status_code == 200
    assert client.get("/api/v1/stories/settings/followers/999999", headers=creator_auth_headers).status_code == 404


def test_close_friend_add_list_remove(client: TestClient, creator_auth_headers):
    assert client.post("/api/v1/stories/settings/close-friends/3", headers=creator_auth_headers).json()["is_close_friend"] is True
    listed = client.get("/api/v1/stories/settings/close-friends", headers=creator_auth_headers).json()
    assert 3 in [person["user_id"] for person in listed]
    assert client.delete("/api/v1/stories/settings/close-friends/3", headers=creator_auth_headers).json()["is_close_friend"] is False
    assert client.post("/api/v1/stories/settings/close-friends/2", headers=creator_auth_headers).status_code == 400


# ------------------------------------------------------------------- push
def test_push_public_key_answers_when_logged_in(client: TestClient, creator_auth_headers):
    response = client.get("/api/v1/messages/push/public-key", headers=creator_auth_headers)
    assert response.status_code == 200
    assert set(response.json()) == {"enabled", "public_key"}


# ------------------------------------------------------------ post archive/pin
def test_archive_restore_pin_unpin_post(client: TestClient, admin_auth_headers):
    created = client.post("/api/v1/posts", data={"post_type": "text", "content": "pin me"}, headers=admin_auth_headers)
    post_id = created.json()["items"][0]["post_id"]

    assert client.post(f"/api/v1/posts/{post_id}/pin", headers=admin_auth_headers).status_code == 200
    assert client.delete(f"/api/v1/posts/{post_id}/pin", headers=admin_auth_headers).status_code == 200
    assert client.post(f"/api/v1/posts/{post_id}/archive", headers=admin_auth_headers).status_code == 200
    assert client.post(f"/api/v1/posts/{post_id}/archive", headers=admin_auth_headers).status_code == 409
    assert client.post(f"/api/v1/posts/{post_id}/restore", headers=admin_auth_headers).status_code == 200
