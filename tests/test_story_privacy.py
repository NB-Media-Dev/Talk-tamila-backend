import pytest
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.common.models.social import Follow, CloseFriend


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


@pytest.fixture(autouse=True)
def clean_social_relations(db_session):
    db_session.query(Follow).delete()
    db_session.query(CloseFriend).delete()
    db_session.commit()
    yield
    db_session.query(Follow).delete()
    db_session.query(CloseFriend).delete()
    db_session.commit()


def test_create_story_privacy_validation(client: TestClient, user1_headers: dict):
    # 1. Valid PUBLIC
    resp = client.post(
        "/api/v1/stories",
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
        "/api/v1/stories",
        json={"content": "Followers Story", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["audience"] == "FOLLOWERS"

    # 3. Valid CLOSE_FRIENDS
    resp = client.post(
        "/api/v1/stories",
        json={"content": "Close Friends Story", "audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["audience"] == "CLOSE_FRIENDS"

    # 4. Invalid Audience -> 422
    resp = client.post(
        "/api/v1/stories",
        json={"content": "Invalid Story", "audience": "EVERYONE_ELSE"},
        headers=user1_headers,
    )
    assert resp.status_code == 422


def test_author_id_cannot_be_manipulated(client: TestClient, user1_headers: dict):
    resp = client.post(
        "/api/v1/stories",
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
    resp = client.post(
        "/api/v1/stories",
        json={"content": "Open to everyone", "audience": "PUBLIC"},
        headers=user1_headers,
    )
    assert resp.status_code == 201
    story_id = resp.json()["id"]

    # User 2 checks feed
    feed_resp = client.get("/api/v1/stories/feed", headers=user2_headers)
    assert feed_resp.status_code == 200
    feed_ids = [s["id"] for s in feed_resp.json()]
    assert story_id in feed_ids

    # User 2 gets single story by ID
    detail_resp = client.get(f"/api/v1/stories/{story_id}", headers=user2_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == story_id


def test_author_always_sees_own_stories(client: TestClient, user1_headers: dict):
    # Create one of each audience type
    resp_pub = client.post(
        "/api/v1/stories",
        json={"content": "My Public Story", "audience": "PUBLIC"},
        headers=user1_headers,
    )
    resp_fol = client.post(
        "/api/v1/stories",
        json={"content": "My Followers Story", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    resp_cf = client.post(
        "/api/v1/stories",
        json={"content": "My Close Friends Story", "audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )

    ids = [resp_pub.json()["id"], resp_fol.json()["id"], resp_cf.json()["id"]]

    # Author checks feed
    feed_resp = client.get("/api/v1/stories/feed", headers=user1_headers)
    assert feed_resp.status_code == 200
    feed_ids = [s["id"] for s in feed_resp.json()]
    for story_id in ids:
        assert story_id in feed_ids

    # Author gets each by ID
    for story_id in ids:
        detail = client.get(f"/api/v1/stories/{story_id}", headers=user1_headers)
        assert detail.status_code == 200


def test_followers_story_visibility(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    user3_headers: dict,
    db_session,
):
    # User 1 creates FOLLOWERS story
    resp = client.post(
        "/api/v1/stories",
        json={"content": "Only for my followers", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    story_id = resp.json()["id"]

    # User 2 (not following) checks feed
    feed_resp2 = client.get("/api/v1/stories/feed", headers=user2_headers)
    assert story_id not in [s["id"] for s in feed_resp2.json()]

    # User 2 attempts direct access -> 403 Forbidden
    detail_resp2 = client.get(f"/api/v1/stories/{story_id}", headers=user2_headers)
    assert detail_resp2.status_code == 403

    # User 2 follows User 1
    follow_resp = client.post("/api/v1/stories/follow/2", headers=user2_headers)
    assert follow_resp.status_code == 200
    assert follow_resp.json().get("user_name") == "Priya"
    db_follow = db_session.query(Follow).filter(Follow.follower_id == 3, Follow.following_id == 2).first()
    assert db_follow is not None
    assert db_follow.user_name == "Priya"

    # User 2 now checks feed -> Story IS visible
    feed_resp2_after = client.get("/api/v1/stories/feed", headers=user2_headers)
    assert story_id in [s["id"] for s in feed_resp2_after.json()]

    # User 2 gets direct detail -> 200 OK
    detail_resp2_after = client.get(f"/api/v1/stories/{story_id}", headers=user2_headers)
    assert detail_resp2_after.status_code == 200

    # User 3 (still not following) cannot see it
    feed_resp3 = client.get("/api/v1/stories/feed", headers=user3_headers)
    assert story_id not in [s["id"] for s in feed_resp3.json()]


def test_close_friends_story_visibility(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    user3_headers: dict,
    db_session,
):
    # User 1 creates CLOSE_FRIENDS story
    resp = client.post(
        "/api/v1/stories",
        json={"content": "Secret close friends only", "audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )
    story_id = resp.json()["id"]

    # User 2 (not in close friends) checks feed
    feed_resp2 = client.get("/api/v1/stories/feed", headers=user2_headers)
    assert story_id not in [s["id"] for s in feed_resp2.json()]

    # User 2 direct access -> 403 Forbidden
    detail_resp2 = client.get(f"/api/v1/stories/{story_id}", headers=user2_headers)
    assert detail_resp2.status_code == 403

    # User 1 adds User 2 to close friends
    add_cf = client.post("/api/v1/stories/settings/close-friends/3", headers=user1_headers)
    assert add_cf.status_code == 200

    # User 2 checks feed -> Story IS visible
    feed_resp2_after = client.get("/api/v1/stories/feed", headers=user2_headers)
    assert story_id in [s["id"] for s in feed_resp2_after.json()]

    # User 2 direct detail -> 200 OK
    detail_resp2_after = client.get(f"/api/v1/stories/{story_id}", headers=user2_headers)
    assert detail_resp2_after.status_code == 200

    # User 3 (not in close friends) still cannot see it
    feed_resp3 = client.get("/api/v1/stories/feed", headers=user3_headers)
    assert story_id not in [s["id"] for s in feed_resp3.json()]
    detail_resp3 = client.get(f"/api/v1/stories/{story_id}", headers=user3_headers)
    assert detail_resp3.status_code == 403

    # User 1 removes User 2 from close friends
    rem_cf = client.delete("/api/v1/stories/settings/close-friends/3", headers=user1_headers)
    assert rem_cf.status_code == 200

    # User 2 no longer sees story
    feed_resp2_removed = client.get("/api/v1/stories/feed", headers=user2_headers)
    assert story_id not in [s["id"] for s in feed_resp2_removed.json()]


def test_feed_pagination(client: TestClient, user1_headers: dict):
    # Create multiple public stories
    for i in range(5):
        client.post(
            "/api/v1/stories",
            json={"content": f"Story page item {i}", "audience": "PUBLIC"},
            headers=user1_headers,
        )

    # Fetch page 1 (limit 2, offset 0)
    page1 = client.get("/api/v1/stories/feed?limit=2&offset=0", headers=user1_headers)
    assert page1.status_code == 200
    items1 = page1.json()
    assert len(items1) == 2

    # Fetch page 2 (limit 2, offset 2)
    page2 = client.get("/api/v1/stories/feed?limit=2&offset=2", headers=user1_headers)
    assert page2.status_code == 200
    items2 = page2.json()
    assert len(items2) == 2

    # Ensure no duplicate items across pages
    ids_page1 = {item["id"] for item in items1}
    ids_page2 = {item["id"] for item in items2}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.fixture
def admin_headers():
    token = create_access_token(1)
    return {"Authorization": f"Bearer {token}"}


def test_change_audience_dynamically_without_affecting_other_stories(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    user3_headers: dict,
    db_session,
):
    # User 1 creates Story A (PUBLIC) and Story B (FOLLOWERS)
    resp_a = client.post(
        "/api/v1/stories",
        json={"content": "Story A", "audience": "PUBLIC"},
        headers=user1_headers,
    )
    assert resp_a.status_code == 201
    story_a_id = resp_a.json()["id"]

    resp_b = client.post(
        "/api/v1/stories",
        json={"content": "Story B", "audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    assert resp_b.status_code == 201
    story_b_id = resp_b.json()["id"]

    feed2 = client.get("/api/v1/stories/feed", headers=user2_headers).json()
    feed2_ids = [s["id"] for s in feed2]
    assert story_a_id in feed2_ids
    assert story_b_id not in feed2_ids

    assert client.get(f"/api/v1/stories/{story_a_id}", headers=user2_headers).status_code == 200
    assert client.get(f"/api/v1/stories/{story_b_id}", headers=user2_headers).status_code == 403

    # User 1 changes Story A from PUBLIC to FOLLOWERS
    patch_a = client.patch(
        f"/api/v1/stories/{story_a_id}",
        json={"audience": "FOLLOWERS"},
        headers=user1_headers,
    )
    assert patch_a.status_code == 200
    assert patch_a.json()["audience"] == "FOLLOWERS"

    # Now User 2 cannot see Story A either
    feed2_after = client.get("/api/v1/stories/feed", headers=user2_headers).json()
    feed2_after_ids = [s["id"] for s in feed2_after]
    assert story_a_id not in feed2_after_ids
    assert client.get(f"/api/v1/stories/{story_a_id}", headers=user2_headers).status_code == 403

    # Story B was NOT affected (still FOLLOWERS)
    detail_b = client.get(f"/api/v1/stories/{story_b_id}", headers=user1_headers).json()
    assert detail_b["audience"] == "FOLLOWERS"

    # User 1 changes Story B to PUBLIC
    patch_b = client.patch(
        f"/api/v1/stories/{story_b_id}",
        json={"audience": "PUBLIC"},
        headers=user1_headers,
    )
    assert patch_b.status_code == 200
    assert patch_b.json()["audience"] == "PUBLIC"

    feed2_after_b = client.get("/api/v1/stories/feed", headers=user2_headers).json()
    feed2_after_b_ids = [s["id"] for s in feed2_after_b]
    assert story_b_id in feed2_after_b_ids
    assert story_a_id not in feed2_after_b_ids
    assert client.get(f"/api/v1/stories/{story_b_id}", headers=user2_headers).status_code == 200
    assert client.get(f"/api/v1/stories/{story_a_id}", headers=user2_headers).status_code == 403

    # User 1 changes Story A to CLOSE_FRIENDS
    patch_a_cf = client.patch(
        f"/api/v1/stories/{story_a_id}",
        json={"audience": "CLOSE_FRIENDS"},
        headers=user1_headers,
    )
    assert patch_a_cf.status_code == 200
    assert patch_a_cf.json()["audience"] == "CLOSE_FRIENDS"

    # User 2 follows User 1
    client.post("/api/v1/stories/follow/2", headers=user2_headers)

    assert client.get(f"/api/v1/stories/{story_a_id}", headers=user2_headers).status_code == 403

    # User 1 adds User 2 to close friends
    client.post("/api/v1/stories/settings/close-friends/3", headers=user1_headers)

    # Now User 2 can see Story A
    assert client.get(f"/api/v1/stories/{story_a_id}", headers=user2_headers).status_code == 200


def test_active_groups_audience_filtering(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    db_session,
):
    # User 1 creates 3 stories: PUBLIC, FOLLOWERS, CLOSE_FRIENDS
    s1 = client.post("/api/v1/stories", json={"content": "Grp Pub", "audience": "PUBLIC"}, headers=user1_headers).json()["id"]
    s2 = client.post("/api/v1/stories", json={"content": "Grp Fol", "audience": "FOLLOWERS"}, headers=user1_headers).json()["id"]
    s3 = client.post("/api/v1/stories", json={"content": "Grp CF", "audience": "CLOSE_FRIENDS"}, headers=user1_headers).json()["id"]

    # 1. Anonymous viewer (no headers) -> Only sees public slides
    anon_resp = client.get("/api/v1/stories")
    assert anon_resp.status_code == 200
    groups = anon_resp.json()
    u1_group = next((g for g in groups if g["id"] == 2), None)
    assert u1_group is not None
    slide_ids = [s["id"] for s in u1_group["slides"]]
    assert s1 in slide_ids
    assert s2 not in slide_ids
    assert s3 not in slide_ids

    u2_resp = client.get("/api/v1/stories", headers=user2_headers)
    assert u2_resp.status_code == 200
    u1_grp2 = next((g for g in u2_resp.json() if g["id"] == 2), None)
    assert u1_grp2 is not None
    slide_ids2 = [s["id"] for s in u1_grp2["slides"]]
    assert s1 in slide_ids2
    assert s2 not in slide_ids2
    assert s3 not in slide_ids2

    client.post("/api/v1/stories/follow/2", headers=user2_headers)
    u2_resp_fol = client.get("/api/v1/stories", headers=user2_headers)
    u1_grp_fol = next((g for g in u2_resp_fol.json() if g["id"] == 2), None)
    slide_ids_fol = [s["id"] for s in u1_grp_fol["slides"]]
    assert s1 in slide_ids_fol
    assert s2 in slide_ids_fol
    assert s3 not in slide_ids_fol

    client.post("/api/v1/stories/settings/close-friends/3", headers=user1_headers)
    u2_resp_all = client.get("/api/v1/stories", headers=user2_headers)
    u1_grp_all = next((g for g in u2_resp_all.json() if g["id"] == 2), None)
    slide_ids_all = [s["id"] for s in u1_grp_all["slides"]]
    assert s1 in slide_ids_all
    assert s2 in slide_ids_all
    assert s3 in slide_ids_all

    # 5. Author (User 1) always sees all 3
    u1_resp = client.get("/api/v1/stories", headers=user1_headers)
    u1_grp_self = next((g for g in u1_resp.json() if g["id"] == 2), None)
    slide_ids_self = [s["id"] for s in u1_grp_self["slides"]]
    assert s1 in slide_ids_self
    assert s2 in slide_ids_self
    assert s3 in slide_ids_self


def test_get_user_stories_audience_filtering(
    client: TestClient,
    user1_headers: dict,
    user2_headers: dict,
    db_session,
):
    s1 = client.post("/api/v1/stories", json={"content": "U Pub", "audience": "PUBLIC"}, headers=user1_headers).json()["id"]
    s2 = client.post("/api/v1/stories", json={"content": "U Fol", "audience": "FOLLOWERS"}, headers=user1_headers).json()["id"]
    s3 = client.post("/api/v1/stories", json={"content": "U CF", "audience": "CLOSE_FRIENDS"}, headers=user1_headers).json()["id"]

    # User 2 not following, not CF
    res1 = client.get("/api/v1/stories/user/2", headers=user2_headers)
    assert res1.status_code == 200
    ids1 = [s["id"] for s in res1.json()]
    assert s1 in ids1
    assert s2 not in ids1
    assert s3 not in ids1

    # User 2 follows User 1
    client.post("/api/v1/stories/follow/2", headers=user2_headers)
    res2 = client.get("/api/v1/stories/user/2", headers=user2_headers)
    ids2 = [s["id"] for s in res2.json()]
    assert s1 in ids2
    assert s2 in ids2
    assert s3 not in ids2

    # User 1 adds User 2 to close friends
    client.post("/api/v1/stories/settings/close-friends/3", headers=user1_headers)
    res3 = client.get("/api/v1/stories/user/2", headers=user2_headers)
    ids3 = [s["id"] for s in res3.json()]
    assert s1 in ids3
    assert s2 in ids3
    assert s3 in ids3


def test_admin_can_view_all_audiences(
    client: TestClient,
    user1_headers: dict,
    admin_headers: dict,
    db_session,
):
    s1 = client.post("/api/v1/stories", json={"content": "Adm Pub", "audience": "PUBLIC"}, headers=user1_headers).json()["id"]
    s2 = client.post("/api/v1/stories", json={"content": "Adm Fol", "audience": "FOLLOWERS"}, headers=user1_headers).json()["id"]
    s3 = client.post("/api/v1/stories", json={"content": "Adm CF", "audience": "CLOSE_FRIENDS"}, headers=user1_headers).json()["id"]

    # Admin checks feed
    feed = client.get("/api/v1/stories/feed", headers=admin_headers).json()
    feed_ids = [s["id"] for s in feed]
    assert s1 in feed_ids
    assert s2 in feed_ids
    assert s3 in feed_ids

    # Admin checks single stories directly
    assert client.get(f"/api/v1/stories/{s1}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/v1/stories/{s2}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/v1/stories/{s3}", headers=admin_headers).status_code == 200

    # Admin checks user endpoint
    user_stories = client.get("/api/v1/stories/user/2", headers=admin_headers).json()
    u_ids = [s["id"] for s in user_stories]
    assert s1 in u_ids
    assert s2 in u_ids
    assert s3 in u_ids


def test_unauthenticated_user_access(
    client: TestClient,
    user1_headers: dict,
    db_session,
):
    s1 = client.post("/api/v1/stories", json={"content": "Open Pub", "audience": "PUBLIC"}, headers=user1_headers).json()["id"]
    s2 = client.post("/api/v1/stories", json={"content": "Closed Fol", "audience": "FOLLOWERS"}, headers=user1_headers).json()["id"]
    s3 = client.post("/api/v1/stories", json={"content": "Closed CF", "audience": "CLOSE_FRIENDS"}, headers=user1_headers).json()["id"]

    # Public story accessible without token
    assert client.get(f"/api/v1/stories/{s1}").status_code == 200

    # Followers / Close Friends stories blocked with 403
    assert client.get(f"/api/v1/stories/{s2}").status_code == 403
    assert client.get(f"/api/v1/stories/{s3}").status_code == 403