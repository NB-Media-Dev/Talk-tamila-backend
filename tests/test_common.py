import pytest
from fastapi.testclient import TestClient

def test_self_and_others_stories_flow(
    client: TestClient,
    creator_auth_headers: dict,
    admin_auth_headers: dict,
    db_session,
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

    my_resp = client.post if False else client.get("/api/stories/my", headers=creator_auth_headers)
    assert my_resp.status_code == 200
    my_stories = my_resp.json()
    assert any(s["id"] == story_id for s in my_stories)

    feed_resp = client.get("/api/stories", headers=creator_auth_headers)
    assert feed_resp.status_code == 200
    groups = feed_resp.json()
    assert len(groups) > 0
    assert groups[0]["is_my_story"] is True
    assert any(slide["id"] == story_id for slide in groups[0]["slides"])

    admin_feed_resp = client.get("/api/stories", headers=admin_auth_headers)
    assert admin_feed_resp.status_code == 200
    admin_groups = admin_feed_resp.json()
    creator_group = next((g for g in admin_groups if any(s["id"] == story_id for s in g["stories"])), None)
    assert creator_group is not None
    assert creator_group["is_my_story"] is False

    single_resp = client.get(f"/api/stories/{story_id}", headers=admin_auth_headers)
    assert single_resp.status_code == 200
    assert single_resp.json()["id"] == story_id

    view_resp = client.post(f"/api/stories/{story_id}/view", headers=admin_auth_headers)
    assert view_resp.status_code == 200
    assert view_resp.json()["success"] is True

    pause_resp = client.post(
        f"/api/stories/{story_id}/pause",
        json={"action": "pause", "progress_ms": 2500, "slide_index": 0},
        headers=admin_auth_headers,
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["success"] is True
    assert pause_resp.json()["action"] == "pause"

    self_like_resp = client.post(f"/api/stories/{story_id}/like", headers=creator_auth_headers)
    assert self_like_resp.status_code == 400
    assert "Cannot like your own story" in self_like_resp.json()["detail"]

    like_resp = client.post(f"/api/stories/{story_id}/like", headers=admin_auth_headers)
    assert like_resp.status_code == 200
    assert like_resp.json()["liked_by_me"] is True

    unlike_resp = client.delete(f"/api/stories/{story_id}/like", headers=admin_auth_headers)
    assert unlike_resp.status_code == 200
    assert unlike_resp.json()["liked_by_me"] is False
    client.post(f"/api/stories/{story_id}/like", headers=admin_auth_headers)

    self_reply_resp = client.post(
        f"/api/stories/{story_id}/comments",
        json={"text": "Self reply"},
        headers=creator_auth_headers,
    )
    assert self_reply_resp.status_code == 400
    assert "Cannot reply to your own story" in self_reply_resp.json()["detail"]

    comment_resp = client.post(
        f"/api/stories/{story_id}/comments",
        json={"text": "Super post! Loved the visuals."},
        headers=admin_auth_headers,
    )
    assert comment_resp.status_code == 201
    assert comment_resp.json()["success"] is True

    share_resp = client.post(
        f"/api/stories/{story_id}/share",
        json={"platform": "whatsapp"},
        headers=admin_auth_headers,
    )
    assert share_resp.status_code == 200
    assert share_resp.json()["success"] is True
    assert share_resp.json()["shares_count"] >= 1

    report_resp = client.post(
        f"/api/stories/{story_id}/report",
        json={"reason": "Inappropriate content", "details": "Testing report flow"},
        headers=admin_auth_headers,
    )
    assert report_resp.status_code == 200
    assert report_resp.json()["success"] is True

    creator_id = created_story["user_id"]
    mute_resp = client.post(f"/api/stories/users/{creator_id}/mute", headers=admin_auth_headers)
    assert mute_resp.status_code == 200
    assert mute_resp.json()["is_muted"] is True

    feed_after_mute = client.get("/api/stories", headers=admin_auth_headers).json()
    assert not any(g["id"] == creator_id for g in feed_after_mute)

    unmute_resp = client.delete(f"/api/stories/users/{creator_id}/mute", headers=admin_auth_headers)
    assert unmute_resp.status_code == 200
    assert unmute_resp.json()["is_muted"] is False

    feed_after_unmute = client.get("/api/stories", headers=admin_auth_headers).json()
    assert any(g["id"] == creator_id for g in feed_after_unmute)

    comments_list_resp = client.get(f"/api/stories/{story_id}/comments")
    assert comments_list_resp.status_code == 200
    comments = comments_list_resp.json()
    assert len(comments) >= 1
    assert any(c["text"] == "Super post! Loved the visuals." for c in comments)

    act_resp = client.get(f"/api/stories/{story_id}/activity", headers=creator_auth_headers)
    assert act_resp.status_code == 200
    act = act_resp.json()
    assert act["total_views"] >= 1
    assert act["total_likes"] >= 1

    save_resp = client.post(f"/api/stories/{story_id}/save", headers=admin_auth_headers)
    assert save_resp.status_code == 200
    assert save_resp.json()["is_saved"] is True

    saved_list_resp = client.get("/api/stories/saved", headers=admin_auth_headers)
    assert saved_list_resp.status_code == 200
    assert any(item["story_id"] == story_id for item in saved_list_resp.json())

    unsave_resp = client.delete(f"/api/stories/{story_id}/save", headers=admin_auth_headers)
    assert unsave_resp.status_code == 200
    assert unsave_resp.json()["is_saved"] is False

    del_forbidden = client.delete(f"/api/stories/{story_id}", headers=admin_auth_headers)
    assert del_forbidden.status_code == 403

    del_resp = client.delete(f"/api/stories/{story_id}", headers=creator_auth_headers)
    get_del_resp = client.get(f"/api/stories/{story_id}")
    assert get_del_resp.status_code == 404

    my_after_del = client.get("/api/stories/my", headers=creator_auth_headers).json()
    assert not any(s["id"] == story_id for s in my_after_del)

    from app.common.models.story import Story
    db_story = db_session.get(Story, story_id)
    assert db_story is not None
    assert db_story.is_deleted is True
    assert db_story.deleted_at is not None
    assert db_story.caption == story_payload["caption"]

def test_unique_story_view_tracking_per_user(
    client: TestClient,
    creator_auth_headers: dict,
    admin_auth_headers: dict,
    influencer_auth_headers: dict,
    db_session,
):
    """Verify story view is counted only once per user for each story:
    - User A views Story X (1st time) -> views_count = 1, 1 DB row
    - User A views Story X (2nd & 3rd time) -> views_count = 1, still 1 DB row
    - User B views Story X (1st time) -> views_count = 2, 2 DB rows
    - User B views Story X (2nd time) -> views_count = 2, still 2 DB rows
    - User A views Story Y (1st time) -> Story Y views_count = 1
    """
    from app.common.models.story import StoryView

    story_x_payload = {
        "media_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "media_type": "image",
        "caption": "Story X",
        "duration_hours": 24,
    }
    resp_x = client.post("/api/stories", json=story_x_payload, headers=creator_auth_headers)
    assert resp_x.status_code == 201
    story_x_id = resp_x.json()["id"]

    story_y_payload = {
        "media_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "media_type": "image",
        "caption": "Story Y",
        "duration_hours": 24,
    }
    resp_y = client.post("/api/stories", json=story_y_payload, headers=creator_auth_headers)
    assert resp_y.status_code == 201
    story_y_id = resp_y.json()["id"]

    view_1 = client.post(f"/api/stories/{story_x_id}/view", headers=admin_auth_headers)
    assert view_1.status_code == 200
    assert view_1.json()["views_count"] == 1

    db_views_x = db_session.query(StoryView).filter(StoryView.story_id == story_x_id).all()
    assert len(db_views_x) == 1

    view_2 = client.post(f"/api/stories/{story_x_id}/view", headers=admin_auth_headers)
    assert view_2.status_code == 200
    assert view_2.json()["views_count"] == 1

    view_3 = client.post(f"/api/stories/{story_x_id}/view", headers=admin_auth_headers)
    assert view_3.status_code == 200
    assert view_3.json()["views_count"] == 1

    db_views_x = db_session.query(StoryView).filter(StoryView.story_id == story_x_id).all()
    assert len(db_views_x) == 1

    view_b1 = client.post(f"/api/stories/{story_x_id}/view", headers=influencer_auth_headers)
    assert view_b1.status_code == 200
    assert view_b1.json()["views_count"] == 2

    db_views_x = db_session.query(StoryView).filter(StoryView.story_id == story_x_id).all()
    assert len(db_views_x) == 2

    view_b2 = client.post(f"/api/stories/{story_x_id}/view", headers=influencer_auth_headers)
    assert view_b2.status_code == 200
    assert view_b2.json()["views_count"] == 2

    db_views_x = db_session.query(StoryView).filter(StoryView.story_id == story_x_id).all()
    assert len(db_views_x) == 2

    view_y1 = client.post(f"/api/stories/{story_y_id}/view", headers=admin_auth_headers)
    assert view_y1.status_code == 200
    assert view_y1.json()["views_count"] == 1

    db_views_y = db_session.query(StoryView).filter(StoryView.story_id == story_y_id).all()
    assert len(db_views_y) == 1

    import pytest
    from datetime import datetime, timezone
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        duplicate_view = StoryView(
            story_id=story_x_id,
            user_id=1,
            user_name="admin",
            viewed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(duplicate_view)
        db_session.commit()
    db_session.rollback()

