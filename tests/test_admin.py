from fastapi.testclient import TestClient


def test_admin_endpoints(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    # 1. Admin overview & stats
    resp = client.get("/api/admin/overview", headers=admin_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "total_stories" in data
    assert "active_stories" in data

    # 2. Non-admin forbidden
    creator_resp = client.get("/api/admin/overview", headers=creator_auth_headers)
    assert creator_resp.status_code == 403


def test_admin_story_management(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    # 1. Creator creates a story
    story_res = client.post(
        "/api/stories",
        json={"content": "Story for Admin moderation", "audience": "PUBLIC"},
        headers=creator_auth_headers,
    )
    assert story_res.status_code == 201
    story_id = story_res.json()["id"]

    # 2. Admin lists all platform stories
    admin_stories = client.get("/api/admin/stories", headers=admin_auth_headers)
    assert admin_stories.status_code == 200
    stories_list = admin_stories.json()
    assert any(s["id"] == story_id for s in stories_list)

    # 3. Admin platform story stats
    stats_res = client.get("/api/admin/stories/stats", headers=admin_auth_headers)
    assert stats_res.status_code == 200
    stats_data = stats_res.json()
    assert stats_data["total_stories"] >= 1

    # 4. Admin deletes story
    del_res = client.delete(f"/api/admin/stories/{story_id}", headers=admin_auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 5. Story is marked deleted in admin list
    deleted_stories = client.get("/api/admin/stories?is_deleted=true", headers=admin_auth_headers)
    assert deleted_stories.status_code == 200
    assert any(s["id"] == story_id and s["is_deleted"] is True for s in deleted_stories.json())

    # 6. Admin restores story
    restore_res = client.patch(f"/api/admin/stories/{story_id}/restore", headers=admin_auth_headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["success"] is True

    # 7. Admin own stories & own stats
    my_stories = client.get("/api/admin/stories/my", headers=admin_auth_headers)
    assert my_stories.status_code == 200

    my_stats = client.get("/api/admin/stories/my/stats", headers=admin_auth_headers)
    assert my_stats.status_code == 200


def test_admin_creates_public_story(client: TestClient, admin_auth_headers: dict):
    """Admin stories are strictly and always PUBLIC broadcast stories."""
    # 1. Admin creates story via /api/admin/stories
    admin_post = client.post(
        "/api/admin/stories",
        json={"content": "Official Announcement from Admin"},
        headers=admin_auth_headers,
    )
    assert admin_post.status_code == 201
    assert admin_post.json()["audience"] == "PUBLIC"

    # 2. Even if an admin specifies FOLLOWERS or CLOSE_FRIENDS, it is enforced to PUBLIC
    forced_post = client.post(
        "/api/stories",
        json={"content": "Admin Broadcast", "audience": "FOLLOWERS"},
        headers=admin_auth_headers,
    )
    assert forced_post.status_code == 201
    assert forced_post.json()["audience"] == "PUBLIC"


