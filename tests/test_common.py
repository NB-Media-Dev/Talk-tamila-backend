import pytest
from fastapi.testclient import TestClient


def test_self_and_others_stories_flow(
    client: TestClient,
    creator_auth_headers: dict,
    admin_auth_headers: dict,
):
    """Thorough validation of Instagram Stories concept:
    - Creator uploads their own story
    - Creator views their own story (self story: GET /api/stories/my and is_my_story==True in feed)
    - Admin (other user/role) views creator's story (GET /api/stories and GET /api/stories/{id})
    - Admin records view (POST /api/stories/{id}/view)
    - Admin likes and unlikes story (POST & DELETE /api/stories/{id}/like)
    - Admin sends reply/comment (POST /api/stories/{id}/comments and GET /api/stories/{id}/comments)
    - Creator inspects viewers and likers activity (GET /api/stories/{id}/activity)
    - Admin (non-author) is forbidden from deleting creator's story (DELETE -> 403)
    - Creator (author) deletes their own story (DELETE -> 204)
    """
    # 1. Creator uploads a story
    story_payload = {
        "media_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "media_type": "image",
        "caption": "My Awesome Instagram Story #TamilNadu",
        "duration_hours": 24,
    }
    upload_resp = client.post("/api/stories", json=story_payload, headers=creator_auth_headers)
    assert upload_resp.status_code == 201
    created_story = upload_resp.json()
    story_id = created_story["id"]
    assert created_story["caption"] == story_payload["caption"]

    # 2. Creator views their own story via /my
    my_resp = client.post if False else client.get("/api/stories/my", headers=creator_auth_headers)
    assert my_resp.status_code == 200
    my_stories = my_resp.json()
    assert any(s["id"] == story_id for s in my_stories)

    # 3. Creator views feed: self story must appear first with is_my_story == True
    feed_resp = client.get("/api/stories", headers=creator_auth_headers)
    assert feed_resp.status_code == 200
    groups = feed_resp.json()
    assert len(groups) > 0
    # First group is creator's own story
    assert groups[0]["is_my_story"] is True
    assert any(slide["id"] == story_id for slide in groups[0]["slides"])

    # 4. Other user (Admin) views the feed: creator's group is NOT their own story (is_my_story == False)
    admin_feed_resp = client.get("/api/stories", headers=admin_auth_headers)
    assert admin_feed_resp.status_code == 200
    admin_groups = admin_feed_resp.json()
    creator_group = next((g for g in admin_groups if any(s["id"] == story_id for s in g["stories"])), None)
    assert creator_group is not None
    assert creator_group["is_my_story"] is False

    # 5. Admin views single story
    single_resp = client.get(f"/api/stories/{story_id}", headers=admin_auth_headers)
    assert single_resp.status_code == 200
    assert single_resp.json()["id"] == story_id

    # 6. Admin marks story as viewed
    view_resp = client.post(f"/api/stories/{story_id}/view", headers=admin_auth_headers)
    assert view_resp.status_code == 200
    assert view_resp.json()["success"] is True

    # 6b. Admin pauses story (playback telemetry)
    pause_resp = client.post(
        f"/api/stories/{story_id}/pause",
        json={"action": "pause", "progress_ms": 2500, "slide_index": 0},
        headers=admin_auth_headers,
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["success"] is True
    assert pause_resp.json()["action"] == "pause"

    # 7. Self-like check: creator cannot like their own story (only for others' stories)
    self_like_resp = client.post(f"/api/stories/{story_id}/like", headers=creator_auth_headers)
    assert self_like_resp.status_code == 400
    assert "Cannot like your own story" in self_like_resp.json()["detail"]

    # 7b. Admin (other user) likes story
    like_resp = client.post(f"/api/stories/{story_id}/like", headers=admin_auth_headers)
    assert like_resp.status_code == 200
    assert like_resp.json()["liked_by_me"] is True

    # 7c. Admin unlikes and re-likes
    unlike_resp = client.delete(f"/api/stories/{story_id}/like", headers=admin_auth_headers)
    assert unlike_resp.status_code == 200
    assert unlike_resp.json()["liked_by_me"] is False
    client.post(f"/api/stories/{story_id}/like", headers=admin_auth_headers)

    # 8. Self-reply check: creator cannot comment/reply to their own story
    self_reply_resp = client.post(
        f"/api/stories/{story_id}/comments",
        json={"text": "Self reply"},
        headers=creator_auth_headers,
    )
    assert self_reply_resp.status_code == 400
    assert "Cannot reply to your own story" in self_reply_resp.json()["detail"]

    # 8b. Admin (other user) comments on story
    comment_resp = client.post(
        f"/api/stories/{story_id}/comments",
        json={"text": "Super post! Loved the visuals."},
        headers=admin_auth_headers,
    )
    assert comment_resp.status_code == 201
    assert comment_resp.json()["success"] is True

    # 8b. Admin shares story (copy link and share to target user)
    share_resp = client.post(
        f"/api/stories/{story_id}/share",
        json={"platform": "whatsapp"},
        headers=admin_auth_headers,
    )
    assert share_resp.status_code == 200
    assert share_resp.json()["success"] is True
    assert share_resp.json()["shares_count"] >= 1

    # 8c. Admin reports story
    report_resp = client.post(
        f"/api/stories/{story_id}/report",
        json={"reason": "Inappropriate content", "details": "Testing report flow"},
        headers=admin_auth_headers,
    )
    assert report_resp.status_code == 200
    assert report_resp.json()["success"] is True

    # 8d. Admin mutes creator -> story disappears from Admin feed
    creator_id = created_story["user_id"]
    mute_resp = client.post(f"/api/stories/users/{creator_id}/mute", headers=admin_auth_headers)
    assert mute_resp.status_code == 200
    assert mute_resp.json()["is_muted"] is True

    feed_after_mute = client.get("/api/stories", headers=admin_auth_headers).json()
    assert not any(g["id"] == creator_id for g in feed_after_mute)

    # Unmute creator -> story appears again
    unmute_resp = client.delete(f"/api/stories/users/{creator_id}/mute", headers=admin_auth_headers)
    assert unmute_resp.status_code == 200
    assert unmute_resp.json()["is_muted"] is False

    feed_after_unmute = client.get("/api/stories", headers=admin_auth_headers).json()
    assert any(g["id"] == creator_id for g in feed_after_unmute)

    # 9. Fetch comments list
    comments_list_resp = client.get(f"/api/stories/{story_id}/comments")
    assert comments_list_resp.status_code == 200
    comments = comments_list_resp.json()
    assert len(comments) >= 1
    assert any(c["text"] == "Super post! Loved the visuals." for c in comments)

    # 10. Creator inspects story activity (viewers & likers)
    act_resp = client.get(f"/api/stories/{story_id}/activity", headers=creator_auth_headers)
    assert act_resp.status_code == 200
    act = act_resp.json()
    assert act["total_views"] >= 1
    assert act["total_likes"] >= 1

    # 10b. Save and unsave story
    save_resp = client.post(f"/api/stories/{story_id}/save", headers=admin_auth_headers)
    assert save_resp.status_code == 200
    assert save_resp.json()["is_saved"] is True

    saved_list_resp = client.get("/api/stories/saved", headers=admin_auth_headers)
    assert saved_list_resp.status_code == 200
    assert any(item["story_id"] == story_id for item in saved_list_resp.json())

    unsave_resp = client.delete(f"/api/stories/{story_id}/save", headers=admin_auth_headers)
    assert unsave_resp.status_code == 200
    assert unsave_resp.json()["is_saved"] is False

    # 11. Admin (non-author) attempts to delete -> 403 Forbidden
    del_forbidden = client.delete(f"/api/stories/{story_id}", headers=admin_auth_headers)
    assert del_forbidden.status_code == 403

    # 12. Creator (author) deletes story -> 204 No Content
    del_resp = client.delete(f"/api/stories/{story_id}", headers=creator_auth_headers)
    assert del_resp.status_code == 204

    # 13. Verify story is deleted
    get_del_resp = client.get(f"/api/stories/{story_id}")
    assert get_del_resp.status_code == 404

