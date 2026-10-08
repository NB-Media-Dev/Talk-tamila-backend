import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.models.moderation import UserBlock
from app.common.models.social import Notification
from app.common.models.story import Story, StoryMention
from app.common.models.user import User
from app.core.security import create_access_token

def get_auth_headers(user_id: int) -> dict:
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}

def test_story_mention_and_reshare_chain(client: TestClient, db_session: Session):
    """
    Full End-to-End Test for the 4-Level Chain:
    A creates Story, mentions B
    -> B receives: 'A mentioned you in their story' (STORY_MENTION)

    B shares A's Story
    -> A receives: 'B shared your story' (STORY_SHARED)

    B mentions C in re-share
    -> C receives: 'B mentioned you in their story' (STORY_MENTION)
    -> A does NOT receive mention notification

    C shares A's Story
    -> A receives: 'C shared your story' (STORY_SHARED)
    -> B does NOT receive STORY_SHARED

    C mentions D
    -> D receives: 'C mentioned you in their story' (STORY_MENTION)

    D shares A's Story
    -> A receives: 'D shared your story' (STORY_SHARED)
    -> B and C do NOT receive STORY_SHARED
    """
    # 1. Setup Users A, B, C, D
    # Seed users: 2=Arjun (A), 3=Priya (B), 4=Karthik (C), 5=Swathi (D)
    user_a = db_session.get(User, 2)
    user_b = db_session.get(User, 3)
    user_c = db_session.get(User, 4)
    user_d = db_session.get(User, 5)

    headers_a = get_auth_headers(user_a.user_id)
    headers_b = get_auth_headers(user_b.user_id)
    headers_c = get_auth_headers(user_c.user_id)
    headers_d = get_auth_headers(user_d.user_id)

    res_a = client.post(
        "/api/v1/stories",
        json={
            "content": f"Hey @{user_b.username} check this out!",
            "media_url": "gradient:insta",
            "audience": "PUBLIC",
            "mentions": [{"username": user_b.username, "x": 0.5, "y": 0.5}],
        },
        headers=headers_a,
    )
    assert res_a.status_code == 201, res_a.text
    story_a_data = res_a.json()
    story_a_id = story_a_data["id"]

    notifs_b = client.get("/api/v1/notifications", headers=headers_b).json()
    mention_b = next((n for n in notifs_b if n["type"] == "STORY_MENTION" and n["reference_id"] == story_a_id), None)
    assert mention_b is not None
    assert f"{user_a.username} mentioned you in their story" in mention_b["message"]
    assert mention_b["actor_id"] == user_a.user_id

    notifs_a = client.get("/api/v1/notifications", headers=headers_a).json()
    assert not any(n["type"] == "STORY_MENTION" and n["reference_id"] == story_a_id for n in notifs_a)

    res_b = client.post(
        f"/api/v1/stories/{story_a_id}/reshare",
        json={
            "caption": f"Re-sharing with @{user_c.username}",
            "audience": "PUBLIC",
            "mentions": [{"username": user_c.username}],
        },
        headers=headers_b,
    )
    assert res_b.status_code == 201, res_b.text
    story_b_data = res_b.json()
    story_b_id = story_b_data["id"]

    assert story_b_data["parent_story_id"] == story_a_id
    assert story_b_data["original_story_id"] == story_a_id
    assert story_b_data["original_owner_id"] == user_a.user_id
    assert story_b_data["is_reshare"] is True

    notifs_a = client.get("/api/v1/notifications", headers=headers_a).json()
    share_a1 = next((n for n in notifs_a if n["type"] == "STORY_SHARED" and n["reference_id"] == story_b_id), None)
    assert share_a1 is not None
    assert f"{user_b.username} shared your story" in share_a1["message"]

    notifs_c = client.get("/api/v1/notifications", headers=headers_c).json()
    mention_c = next((n for n in notifs_c if n["type"] == "STORY_MENTION" and n["reference_id"] == story_b_id), None)
    assert mention_c is not None
    assert f"{user_b.username} mentioned you in their story" in mention_c["message"]

    assert not any(n["type"] == "STORY_MENTION" and n["reference_id"] == story_b_id for n in notifs_a)

    res_c = client.post(
        f"/api/v1/stories/{story_b_id}/reshare",
        json={
            "caption": f"Pass it on to @{user_d.username}",
            "audience": "PUBLIC",
            "mentions": [{"username": user_d.username}],
        },
        headers=headers_c,
    )
    assert res_c.status_code == 201, res_c.text
    story_c_data = res_c.json()
    story_c_id = story_c_data["id"]

    assert story_c_data["parent_story_id"] == story_b_id
    assert story_c_data["original_story_id"] == story_a_id
    assert story_c_data["original_owner_id"] == user_a.user_id
    assert story_c_data["is_reshare"] is True

    notifs_a = client.get("/api/v1/notifications", headers=headers_a).json()
    share_a2 = next((n for n in notifs_a if n["type"] == "STORY_SHARED" and n["reference_id"] == story_c_id), None)
    assert share_a2 is not None
    assert f"{user_c.username} shared your story" in share_a2["message"]

    notifs_b = client.get("/api/v1/notifications", headers=headers_b).json()
    assert not any(n["type"] == "STORY_SHARED" and n["reference_id"] == story_c_id for n in notifs_b)

    notifs_d = client.get("/api/v1/notifications", headers=headers_d).json()
    mention_d = next((n for n in notifs_d if n["type"] == "STORY_MENTION" and n["reference_id"] == story_c_id), None)
    assert mention_d is not None
    assert f"{user_c.username} mentioned you in their story" in mention_d["message"]

    res_d = client.post(
        f"/api/v1/stories/{story_c_id}/reshare",
        json={
            "caption": "Re-shared by D!",
            "audience": "PUBLIC",
        },
        headers=headers_d,
    )
    assert res_d.status_code == 201, res_d.text
    story_d_data = res_d.json()
    story_d_id = story_d_data["id"]

    assert story_d_data["parent_story_id"] == story_c_id
    assert story_d_data["original_story_id"] == story_a_id
    assert story_d_data["original_owner_id"] == user_a.user_id
    assert story_d_data["is_reshare"] is True

    notifs_a = client.get("/api/v1/notifications", headers=headers_a).json()
    share_a3 = next((n for n in notifs_a if n["type"] == "STORY_SHARED" and n["reference_id"] == story_d_id), None)
    assert share_a3 is not None
    assert f"{user_d.username} shared your story" in share_a3["message"]

    notifs_b = client.get("/api/v1/notifications", headers=headers_b).json()
    assert not any(n["type"] == "STORY_SHARED" and n["reference_id"] == story_d_id for n in notifs_b)
    notifs_c = client.get("/api/v1/notifications", headers=headers_c).json()
    assert not any(n["type"] == "STORY_SHARED" and n["reference_id"] == story_d_id for n in notifs_c)

    del_res = client.delete(f"/api/v1/stories/{story_a_id}", headers=headers_a)
    assert del_res.status_code == 204

    assert client.get(f"/api/v1/stories/{story_a_id}", headers=headers_a).status_code == 404
    assert client.get(f"/api/v1/stories/{story_b_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/stories/{story_c_id}", headers=headers_c).status_code == 404
    assert client.get(f"/api/v1/stories/{story_d_id}", headers=headers_d).status_code == 404

    feed_b = client.get("/api/v1/stories/my", headers=headers_b).json()
    assert not any(s["id"] == story_b_id for s in feed_b)
    feed_c = client.get("/api/v1/stories/my", headers=headers_c).json()
    assert not any(s["id"] == story_c_id for s in feed_c)
    feed_d = client.get("/api/v1/stories/my", headers=headers_d).json()
    assert not any(s["id"] == story_d_id for s in feed_d)

    reshare_deleted = client.post(
        f"/api/v1/stories/{story_a_id}/reshare",
        json={"caption": "Try re-sharing deleted"},
        headers=headers_b,
    )
    assert reshare_deleted.status_code in (400, 404)

def test_story_expiration_invalidates_derived_stories(client: TestClient, db_session: Session):
    """Ensure that when original Story expires, all derived stories become unavailable."""
    user_a = db_session.get(User, 2)
    user_b = db_session.get(User, 3)
    headers_a = get_auth_headers(user_a.user_id)
    headers_b = get_auth_headers(user_b.user_id)

    res_a = client.post(
        "/api/v1/stories",
        json={
            "content": f"Story A expiring @{user_b.username}",
            "media_url": "gradient:sunset",
            "audience": "PUBLIC",
            "mentions": [{"username": user_b.username}],
        },
        headers=headers_a,
    ).json()
    story_a_id = res_a["id"]

    res_b = client.post(
        f"/api/v1/stories/{story_a_id}/reshare",
        json={"caption": "Story B re-share"},
        headers=headers_b,
    ).json()
    story_b_id = res_b["id"]

    assert client.get(f"/api/v1/stories/{story_b_id}", headers=headers_b).status_code == 200

    story_a = db_session.get(Story, story_a_id)
    story_a.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    db_session.commit()

    assert client.get(f"/api/v1/stories/{story_a_id}", headers=headers_a).status_code == 404
    assert client.get(f"/api/v1/stories/{story_b_id}", headers=headers_b).status_code == 404

    reshare_expired = client.post(
        f"/api/v1/stories/{story_a_id}/reshare",
        json={"caption": "Try re-sharing expired"},
        headers=headers_b,
    )
    assert reshare_expired.status_code == 400

def test_privacy_and_block_restrictions_for_mentions_and_reshare(client: TestClient, db_session: Session):
    """Ensure blocked users cannot be mentioned and blocked users cannot re-share."""
    user_a = db_session.get(User, 2)
    user_blocked = db_session.get(User, 6)

    headers_a = get_auth_headers(user_a.user_id)
    headers_blocked = get_auth_headers(user_blocked.user_id)

    block = UserBlock(blocker_id=user_a.user_id, blocked_id=user_blocked.user_id)
    db_session.add(block)
    db_session.commit()

    res_mention_blocked = client.post(
        "/api/v1/stories",
        json={
            "content": f"Hey @{user_blocked.username}",
            "media_url": "gradient:insta",
            "mentions": [{"username": user_blocked.username}],
        },
        headers=headers_a,
    )
    assert res_mention_blocked.status_code == 400
    assert "blocked" in res_mention_blocked.text.lower()

    res_ok = client.post(
        "/api/v1/stories",
        json={"content": "Clean story", "media_url": "gradient:insta", "audience": "PUBLIC"},
        headers=headers_a,
    ).json()
    story_id = res_ok["id"]

    res_reshare_blocked = client.post(
        f"/api/v1/stories/{story_id}/reshare",
        json={"caption": "Trying to reshare while blocked"},
        headers=headers_blocked,
    )
    assert res_reshare_blocked.status_code == 403

    db_session.delete(block)
    db_session.commit()

def test_mention_user_search(client: TestClient, db_session: Session):
    """Test user autocomplete search for mentions and is_already_mentioned flag."""
    user_a = db_session.get(User, 2)
    user_b = db_session.get(User, 3)
    headers_a = get_auth_headers(user_a.user_id)

    res = client.get(f"/api/v1/stories/mentions/search?q={user_b.username}", headers=headers_a)
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 1
    target = next((u for u in users if u["user_id"] == user_b.user_id), None)
    assert target is not None
    assert target["is_already_mentioned"] is False

    res_story = client.post(
        "/api/v1/stories/",
        json={
            "content": "Story with mention test",
            "media_url": "gradient:sunset",
            "audience": "PUBLIC",
            "mentions": [{"user_id": user_b.user_id, "username": user_b.username}],
        },
        headers=headers_a,
    )
    assert res_story.status_code == 201
    story_id = res_story.json()["id"]

    res_search_story = client.get(
        f"/api/v1/stories/mentions/search?q={user_b.username}&story_id={story_id}",
        headers=headers_a,
    )
    assert res_search_story.status_code == 200
    users_story = res_search_story.json()
    target_in_story = next((u for u in users_story if u["user_id"] == user_b.user_id), None)
    assert target_in_story is not None
    assert target_in_story["is_already_mentioned"] is True

def test_only_mentioned_story_can_be_reshared(client: TestClient, db_session: Session):
    """
    Ensure:
    Story 1 -> A does NOT mention B
    Story 2 -> A mentions B
    Story 3 -> A does NOT mention B

    B can re-share Story 2 (201 Created)
    B CANNOT re-share Story 1 (403 Forbidden: RESHARE_NOT_ALLOWED)
    B CANNOT re-share Story 3 (403 Forbidden: RESHARE_NOT_ALLOWED)
    """
    user_a = db_session.get(User, 2)
    user_b = db_session.get(User, 3)

    headers_a = get_auth_headers(user_a.user_id)
    headers_b = get_auth_headers(user_b.user_id)

    res_1 = client.post(
        "/api/v1/stories",
        json={"content": "Story 1 - No mention", "media_url": "gradient:insta", "audience": "PUBLIC"},
        headers=headers_a,
    )
    assert res_1.status_code == 201
    story_1_id = res_1.json()["id"]

    res_2 = client.post(
        "/api/v1/stories",
        json={
            "content": f"Story 2 - Hey @{user_b.username}!",
            "media_url": "gradient:sunset",
            "audience": "PUBLIC",
            "mentions": [{"username": user_b.username}],
        },
        headers=headers_a,
    )
    assert res_2.status_code == 201
    story_2_id = res_2.json()["id"]

    res_3 = client.post(
        "/api/v1/stories",
        json={"content": "Story 3 - No mention", "media_url": "gradient:cyber", "audience": "PUBLIC"},
        headers=headers_a,
    )
    assert res_3.status_code == 201
    story_3_id = res_3.json()["id"]

    res_b_share_1 = client.post(
        f"/api/v1/stories/{story_1_id}/reshare",
        json={"caption": "Attempting to re-share Story 1"},
        headers=headers_b,
    )
    assert res_b_share_1.status_code == 403
    assert "RESHARE_NOT_ALLOWED" in res_b_share_1.text

    res_b_share_3 = client.post(
        f"/api/v1/stories/{story_3_id}/reshare",
        json={"caption": "Attempting to re-share Story 3"},
        headers=headers_b,
    )
    assert res_b_share_3.status_code == 403
    assert "RESHARE_NOT_ALLOWED" in res_b_share_3.text

    res_b_share_2 = client.post(
        f"/api/v1/stories/{story_2_id}/reshare",
        json={"caption": "Re-sharing Story 2 where I was mentioned"},
        headers=headers_b,
    )
    assert res_b_share_2.status_code == 201
    assert res_b_share_2.json()["parent_story_id"] == story_2_id

    # Attempting to re-share again while still active on profile should fail with 400 ALREADY_RESHARED
    res_b_share_2_again = client.post(
        f"/api/v1/stories/{story_2_id}/reshare",
        json={"caption": "Attempting to re-share Story 2 again"},
        headers=headers_b,
    )
    assert res_b_share_2_again.status_code == 400
    assert "ALREADY_RESHARED" in res_b_share_2_again.text

