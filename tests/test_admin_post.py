from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.common.models.user import User


def test_admin_create_post_success(client: TestClient, admin_auth_headers: dict, db_session: Session):
    """Verify that admin can upload/create a post and it is public under admin's ID."""
    payload = {
        "title": "Welcome to Talk Tamila Admin Announcement",
        "caption": "Exciting new features launched! #TalkTamila #Update #Chennai",
        "media_type": "image",
        "media_url": "https://example.com/admin_post.png",
        "platforms": ["Talk Tamila", "Instagram", "Facebook"],
    }
    resp = client.post("/api/admin/posts", json=payload, headers=admin_auth_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["user_id"] == 1
    assert data["author_id"] == 1
    assert data["title"] == payload["title"]
    assert data["audience"] == "PUBLIC"
    assert data["status"] == "published"
    assert "TalkTamila" in data["tags"] or "Chennai" in data["tags"]
    assert data["author"]["role"] == "admin"


def test_non_admin_cannot_create_admin_post(client: TestClient, creator_auth_headers: dict):
    """Verify non-admin cannot use admin post endpoint."""
    payload = {
        "title": "Attempt by non-admin",
        "caption": "Should be forbidden",
    }
    resp = client.post("/api/admin/posts", json=payload, headers=creator_auth_headers)
    assert resp.status_code == 403


def test_public_feed_shows_admin_post_to_others(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    """Verify that when admin uploads post, it appears in universal feed for everyone."""
    # 1. Admin creates post
    create_resp = client.post(
        "/api/admin/posts",
        json={
            "title": "Public Feed Announcement",
            "caption": "Visible to all creators and users #Community",
            "media_type": "image",
        },
        headers=admin_auth_headers,
    )
    assert create_resp.status_code == 201

    # 2. Regular user fetches public feed
    resp = client.get("/api/posts", headers=creator_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert any(p["title"] == "Public Feed Announcement" for p in data["items"])

    # 3. Anonymous / Guest user can also fetch public feed
    guest_resp = client.get("/api/posts")
    assert guest_resp.status_code == 200
    guest_data = guest_resp.json()
    assert any(p["title"] == "Public Feed Announcement" for p in guest_data["items"])


def test_user_profile_shows_posts(client: TestClient, admin_auth_headers: dict, db_session: Session):
    """Verify that visiting admin's profile returns the admin's posts."""
    admin_user = db_session.get(User, 1)
    client.post(
        "/api/admin/posts",
        json={
            "title": "Admin Profile Showcase Post",
            "caption": "On Admin profile tab",
            "media_type": "image",
        },
        headers=admin_auth_headers,
    )

    resp = client.get(f"/api/users/by-username/{admin_user.username}/posts", headers=admin_auth_headers)
    assert resp.status_code == 200
    posts = resp.json()
    assert len(posts) > 0
    assert any(p["title"] == "Admin Profile Showcase Post" for p in posts)


def test_like_and_comment_on_admin_post(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    """Verify other users can interact (like, comment, save, share) on the admin post."""
    # 1. Admin creates post
    create_resp = client.post(
        "/api/admin/posts",
        json={
            "title": "Interactable Post",
            "caption": "Leave a comment!",
        },
        headers=admin_auth_headers,
    )
    assert create_resp.status_code == 201
    post_id = create_resp.json()["id"]

    # 2. Regular user likes the post
    like_resp = client.post(f"/api/posts/{post_id}/like", headers=creator_auth_headers)
    assert like_resp.status_code == 200
    assert like_resp.json()["liked"] is True
    assert like_resp.json()["likes_count"] == 1

    # 3. Regular user adds a comment
    comment_resp = client.post(
        f"/api/posts/{post_id}/comment",
        json={"comment_text": "Great update from Admin!"},
        headers=creator_auth_headers,
    )
    assert comment_resp.status_code == 200
    assert comment_resp.json()["comment_text"] == "Great update from Admin!"

    # 4. Check comments list
    comments_list = client.get(f"/api/posts/{post_id}/comments")
    assert comments_list.status_code == 200
    assert len(comments_list.json()) == 1

    # 5. Regular user saves the post
    save_resp = client.post(f"/api/posts/{post_id}/save", headers=creator_auth_headers)
    assert save_resp.status_code == 200
    assert save_resp.json()["saved"] is True

    # 6. Regular user shares the post
    share_resp = client.post(f"/api/posts/{post_id}/share", json={"platform": "Talk Tamila"}, headers=creator_auth_headers)
    assert share_resp.status_code == 200
    assert share_resp.json()["shares_count"] >= 1
