import pytest
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.common.models.social import Follow, CloseFriend
from app.common.models.story import Story
from app.common.models.user import User


@pytest.fixture
def user1_headers():
    # user_id 2 (creator)
    token = create_access_token(2)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user2_headers():
    # user_id 3 (influencer)
    token = create_access_token(3)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user3_headers():
    # user_id 4 (freelancer)
    token = create_access_token(4)
    return {"Authorization": f"Bearer {token}"}


def test_create_story_privacy_validation(client: TestClient, user1_headers: dict):
    """Test audience validation: must accept only PUBLIC, FOLLOWERS, CLOSE_FRIENDS."""
    # 1. Valid PUBLIC
    resp = client.post(
        "/api/stories",
        json={"content": "Public Story", "audience": "PUBLIC"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["audience"] == "PUBLIC"
    assert data["content"] == "Public Story"
    assert data["author_id"] == 2
    assert data["user_id"] == 2

    # 2. Valid FOLLOWERS
    resp = client.post(
        "/api/stories",
        json={"content": "Followers Story", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["audience"] == "FOLLOWERS"

    # 3. Valid CLOSE_FRIENDS
    resp = client.post(
        "/api/stories",
        json={"content": "Close Friends Story", "audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["audience"] == "CLOSE_FRIENDS"

    # 4. Invalid Audience -> 422
    resp = client.post(
        "/api/stories",
        json={"content": "Invalid Story", "audience": "EVERYONE_ELSE"},
        headers=user1_headers,
    )
    assert resp.status_code == 422


def test_author_id_cannot_be_manipulated(client: TestClient, user1_headers: dict):
    """Client cannot spoof author_id / user_id by passing it in request body."""
    resp = client.post(
        "/api/stories",
        json={
            "content": "Trying to spoof author",
            "audience": "PUBLIC",
            "author_id": 999,
            "user_id": 999,
        },
        headers=user1_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    # Stored strictly as user 2 (authenticated user)
    assert data["author_id"] == 2
    assert data["user_id"] == 2


def test_public_story_visibility(client: TestClient, user1_headers: dict, user2_headers: dict):
    """PUBLIC story created by user1 is visible to user2 in feed and by ID."""
    resp = client.post(
        "/api/stories",
        json={"content": "Open to everyone", "audience": "PUBLIC"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    story_id = resp.json()["id"]

    # User 2 checks feed
    feed_resp = client.get("/api/stories/feed", headers=user2_headers)
    assert feed_resp.status_code == 200
    feed_ids = [s["id"] for s in feed_resp.json()]
    assert story_id in feed_ids

    # User 2 gets single story by ID
    detail_resp = client.get(f"/api/stories/{story_id}", headers=user2_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == story_id


def test_author_always_sees_own_stories(client: TestClient, user1_headers: dict):
    """Author can always see their own stories regardless of audience."""
    # Create one of each audience type
    resp_pub = client.post(
        "/api/stories",
        json={"content": "My Public Story", "audience": "PUBLIC"},
        headers=user1_headers,
    )
    resp_fol = client.post(
        "/api/stories",
        json={"content": "My Followers Story", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    resp_cf = client.post(
        "/api/stories",
        json={"content": "My Close Friends Story", "audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )

    ids = [resp_pub.json()["id"], resp_fol.json()["id"], resp_cf.json()["id"]]

    # Author checks feed
    feed_resp = client.get("/api/stories/feed", headers=user1_headers)
    assert feed_resp.status_code == 200
    feed_ids = [s["id"] for s in feed_resp.json()]
    for story_id in ids:
        assert story_id in feed_ids

    # Author gets each by ID
    for story_id in ids:
        detail = client.get(f"/api/stories/{story_id}", headers=user1_headers)
        assert detail.status_code == 200


def test_followers_story_visibility(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    user3_headers: dict,
    db_session,
):
    """FOLLOWERS story:
    - Visible only when user actively follows author.
    - Not visible when user does not follow author.
    """
    # User 1 creates FOLLOWERS story
    resp = client.post(
        "/api/stories",
        json={"content": "Only for my followers", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    story_id = resp.json()["id"]

    # User 2 (not following) checks feed
    feed_resp2 = client.get("/api/stories/feed", headers=user2_headers)
    assert story_id not in [s["id"] for s in feed_resp2.json()]

    # User 2 attempts direct access -> 403 Forbidden
    detail_resp2 = client.get(f"/api/stories/{story_id}", headers=user2_headers)
    assert detail_resp2.status_code == 403

    # User 2 follows User 1
    follow_resp = client.post("/api/stories/follow/2", headers=user2_headers)
    assert follow_resp.status_code == 200

    # User 2 now checks feed -> Story IS visible
    feed_resp2_after = client.get("/api/stories/feed", headers=user2_headers)
    assert story_id in [s["id"] for s in feed_resp2_after.json()]

    # User 2 gets direct detail -> 200 OK
    detail_resp2_after = client.get(f"/api/stories/{story_id}", headers=user2_headers)
    assert detail_resp2_after.status_code == 200

    # User 3 (still not following) cannot see it
    feed_resp3 = client.get("/api/stories/feed", headers=user3_headers)
    assert story_id not in [s["id"] for s in feed_resp3.json()]


def test_close_friends_story_visibility(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    user3_headers: dict,
    db_session,
):
    """CLOSE_FRIENDS story:
    - Visible only when author explicitly added user to close friends.
    - Not visible when author has not added user.
    """
    # User 1 creates CLOSE_FRIENDS story
    resp = client.post(
        "/api/stories",
        json={"content": "Secret close friends only", "audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )
    story_id = resp.json()["id"]

    # User 2 (not in close friends) checks feed
    feed_resp2 = client.get("/api/stories/feed", headers=user2_headers)
    assert story_id not in [s["id"] for s in feed_resp2.json()]

    # User 2 direct access -> 403 Forbidden
    detail_resp2 = client.get(f"/api/stories/{story_id}", headers=user2_headers)
    assert detail_resp2.status_code == 403

    # User 1 adds User 2 to close friends
    add_cf = client.post("/api/stories/close-friends/3", headers=user1_headers)
    assert add_cf.status_code == 200

    # User 2 checks feed -> Story IS visible
    feed_resp2_after = client.get("/api/stories/feed", headers=user2_headers)
    assert story_id in [s["id"] for s in feed_resp2_after.json()]

    # User 2 direct detail -> 200 OK
    detail_resp2_after = client.get(f"/api/stories/{story_id}", headers=user2_headers)
    assert detail_resp2_after.status_code == 200

    # User 3 (not in close friends) still cannot see it
    feed_resp3 = client.get("/api/stories/feed", headers=user3_headers)
    assert story_id not in [s["id"] for s in feed_resp3.json()]
    detail_resp3 = client.get(f"/api/stories/{story_id}", headers=user3_headers)
    assert detail_resp3.status_code == 403

    # User 1 removes User 2 from close friends
    rem_cf = client.delete("/api/stories/close-friends/3", headers=user1_headers)
    assert rem_cf.status_code == 200

    # User 2 no longer sees story
    feed_resp2_removed = client.get("/api/stories/feed", headers=user2_headers)
    assert story_id not in [s["id"] for s in feed_resp2_removed.json()]


def test_feed_pagination(client: TestClient, user1_headers: dict):
    """Test pagination with limit and offset."""
    # Create multiple public stories
    for i in range(5):
        client.post(
            "/api/stories",
            json={"content": f"Story page item {i}", "audience": "PUBLIC"},
            headers=user1_headers,
        )

    # Fetch page 1 (limit 2, offset 0)
    page1 = client.get("/api/stories/feed?limit=2&offset=0", headers=user1_headers)
    assert page1.status_code == 200
    items1 = page1.json()
    assert len(items1) == 2

    # Fetch page 2 (limit 2, offset 2)
    page2 = client.get("/api/stories/feed?limit=2&offset=2", headers=user1_headers)
    assert page2.status_code == 200
    items2 = page2.json()
    assert len(items2) == 2

    # Ensure no duplicate items across pages
    ids_page1 = {item["id"] for item in items1}
    ids_page2 = {item["id"] for item in items2}
    assert ids_page1.isdisjoint(ids_page2)
