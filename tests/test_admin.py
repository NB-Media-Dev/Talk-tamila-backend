from fastapi.testclient import TestClient

def test_admin_endpoints(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    resp = client.get("/api/admin/stories/stats", headers=admin_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_stories" in data
    assert "active_stories" in data

    creator_resp = client.get("/api/admin/stories/stats", headers=creator_auth_headers)
    assert creator_resp.status_code == 403


def test_admin_story_management(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    story_res = client.post(
        "/api/stories",
        json={"content": "Story for Admin moderation", "audience": "PUBLIC"},
        headers=creator_auth_headers,
    )
    assert story_res.status_code == 201
    story_id = story_res.json()["id"]

    admin_stories = client.get("/api/admin/stories", headers=admin_auth_headers)
    assert admin_stories.status_code == 200
    stories_list = admin_stories.json()
    assert any(s["id"] == story_id for s in stories_list)

    stats_res = client.get("/api/admin/stories/stats", headers=admin_auth_headers)
    assert stats_res.status_code == 200
    stats_data = stats_res.json()
    assert stats_data["total_stories"] >= 1

    del_res = client.delete(f"/api/admin/stories/{story_id}", headers=admin_auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    deleted_stories = client.get("/api/admin/stories?is_deleted=true", headers=admin_auth_headers)
    assert deleted_stories.status_code == 200
    assert any(s["id"] == story_id and s["is_deleted"] is True for s in deleted_stories.json())

    restore_res = client.patch(f"/api/admin/stories/{story_id}/restore", headers=admin_auth_headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["success"] is True

    my_stories = client.get("/api/admin/stories/my", headers=admin_auth_headers)
    assert my_stories.status_code == 200

    my_stats = client.get("/api/admin/stories/my/stats", headers=admin_auth_headers)
    assert my_stats.status_code == 200

def test_admin_creates_public_story(client: TestClient, admin_auth_headers: dict):
    # 1. Admin creates story via /api/admin/stories
    admin_post = client.post(
        "/api/admin/stories",
        json={"content": "Official Announcement from Admin"},
        headers=admin_auth_headers,
    )
    assert admin_post.status_code == 201
    assert admin_post.json()["audience"] == "PUBLIC"

    forced_post = client.post(
        "/api/stories",
        json={"content": "Admin Broadcast", "audience": "FOLLOWERS"},
        headers=admin_auth_headers,
    )
    assert forced_post.status_code == 201
    assert forced_post.json()["audience"] == "PUBLIC"


def test_admin_send_story_warning(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    story_res = client.post(
        "/api/stories",
        json={"content": "Story for warning test", "audience": "PUBLIC"},
        headers=creator_auth_headers,
    )
    assert story_res.status_code == 201
    story_id = story_res.json()["id"]

    warn_res = client.post(
        f"/api/admin/stories/{story_id}/warn",
        json={"message": "Please remove inappropriate text from this story.", "warning_type": "guidelines"},
        headers=admin_auth_headers,
    )
    assert warn_res.status_code == 200
    warn_data = warn_res.json()
    assert warn_data["success"] is True
    assert warn_data["story_id"] == story_id
    assert "user_id" in warn_data

    # Verify notification exists for creator
    notifs_res = client.get("/api/notifications", headers=creator_auth_headers)
    assert notifs_res.status_code == 200
    notifs = notifs_res.json()
    assert any(n.get("type") == "story_warning" and n.get("reference_id") == story_id for n in notifs)


def test_admin_ban_and_unban_user(client: TestClient, admin_auth_headers: dict):
    # Ban user 2
    ban_res = client.patch("/api/admin/users/2/ban", headers=admin_auth_headers)
    assert ban_res.status_code == 200
    assert ban_res.json()["success"] is True

    # Unban user 2
    unban_res = client.patch("/api/admin/users/2/unban", headers=admin_auth_headers)
    assert unban_res.status_code == 200
    assert unban_res.json()["success"] is True



