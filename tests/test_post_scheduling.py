from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.common.models.post import Post
from app.common.services.post_service import PostService

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _when(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat(timespec="seconds")


def _create(client: TestClient, headers: dict, **data):
    files = data.pop("files", None)
    return client.post("/api/v1/posts", data=data, files=files, headers=headers)


def _schedule(client, headers, content, **delta):
    r = _create(client, headers, post_type="text", content=content, scheduled_at=_when(**(delta or {"hours": 2})))
    assert r.status_code == 201, r.text
    return r.json()["items"][0]


def _count(client, headers) -> int:
    return client.get("/api/v1/auth/profile", headers=headers).json()["posts_count"]


def _feed_ids(client, headers) -> list:
    return [p["post_id"] for p in client.get("/api/v1/posts?limit=30", headers=headers).json()["items"]]


def test_scheduled_post_is_hidden_and_not_counted(client: TestClient, admin_auth_headers, influencer_auth_headers):
    before = _count(client, admin_auth_headers)
    post = _schedule(client, admin_auth_headers, "sched-hidden")
    assert post["status"] == "scheduled"
    assert post["published_at"] is None
    assert post["scheduled_at"].endswith("Z")

    assert post["post_id"] not in _feed_ids(client, admin_auth_headers)
    assert post["post_id"] not in _feed_ids(client, influencer_auth_headers)
    assert _count(client, admin_auth_headers) == before

    listed = client.get("/api/v1/posts/scheduled", headers=admin_auth_headers).json()
    assert any(p["post_id"] == post["post_id"] for p in listed["items"])
    assert listed["total"] >= 1


def test_without_scheduled_at_publishes_immediately(client: TestClient, admin_auth_headers):
    before = _count(client, admin_auth_headers)
    r = _create(client, admin_auth_headers, post_type="text", content="sched-now")
    post = r.json()["items"][0]
    assert post["status"] == "published" and post["published_at"].endswith("Z")
    assert post["post_id"] in _feed_ids(client, admin_auth_headers)
    assert _count(client, admin_auth_headers) == before + 1


def test_bad_schedule_times_are_rejected(client: TestClient, admin_auth_headers):
    naive = (datetime.now() + timedelta(hours=3)).replace(tzinfo=None).isoformat(timespec="seconds")
    cases = [
        naive,                      # no timezone
        _when(seconds=10),          # less than 1 minute ahead
        _when(minutes=-30),         # in the past
        _when(days=400),            # more than 365 days ahead
        "tomorrow evening",         # not a date
    ]
    for value in cases:
        r = _create(client, admin_auth_headers, post_type="text", content="sched-bad", scheduled_at=value)
        assert r.status_code == 400, (value, r.text)


def test_zulu_time_is_accepted(client: TestClient, admin_auth_headers):
    when = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = _create(client, admin_auth_headers, post_type="text", content="sched-z", scheduled_at=when)
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["scheduled_at"] == when


def test_only_admins_manage_schedule(client: TestClient, admin_auth_headers, influencer_auth_headers):
    post = _schedule(client, admin_auth_headers, "sched-perm")
    pid = post["post_id"]
    assert client.get("/api/v1/posts/scheduled", headers=influencer_auth_headers).status_code == 403
    assert client.patch(f"/api/v1/posts/{pid}/schedule", json={"scheduled_at": _when(hours=4)},
                        headers=influencer_auth_headers).status_code == 403
    assert client.post(f"/api/v1/posts/{pid}/publish", headers=influencer_auth_headers).status_code == 403
    # a non-admin cannot even tell the scheduled post exists
    assert client.delete(f"/api/v1/posts/{pid}", headers=influencer_auth_headers).status_code == 404
    assert client.get("/api/v1/posts/scheduled").status_code == 401


def test_reschedule(client: TestClient, admin_auth_headers):
    post = _schedule(client, admin_auth_headers, "sched-move")
    new_time = _when(days=3)
    r = client.patch(f"/api/v1/posts/{post['post_id']}/schedule", json={"scheduled_at": new_time}, headers=admin_auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["status"] == "scheduled"

    bad = client.patch(f"/api/v1/posts/{post['post_id']}/schedule",
                       json={"scheduled_at": "2030-01-01T10:00:00"}, headers=admin_auth_headers)
    assert bad.status_code == 422
    soon = client.patch(f"/api/v1/posts/{post['post_id']}/schedule",
                        json={"scheduled_at": _when(seconds=5)}, headers=admin_auth_headers)
    assert soon.status_code == 400
    assert client.patch("/api/v1/posts/999999/schedule", json={"scheduled_at": new_time},
                        headers=admin_auth_headers).status_code == 404


def test_publish_now_goes_live_once(client: TestClient, admin_auth_headers, influencer_auth_headers):
    before = _count(client, admin_auth_headers)
    post = _schedule(client, admin_auth_headers, "sched-publish-now")
    r = client.post(f"/api/v1/posts/{post['post_id']}/publish", headers=admin_auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["status"] == "published"
    assert post["post_id"] in _feed_ids(client, influencer_auth_headers)
    assert _count(client, admin_auth_headers) == before + 1

    again = client.post(f"/api/v1/posts/{post['post_id']}/publish", headers=admin_auth_headers)
    assert again.status_code == 409
    assert _count(client, admin_auth_headers) == before + 1
    reschedule = client.patch(f"/api/v1/posts/{post['post_id']}/schedule",
                              json={"scheduled_at": _when(days=1)}, headers=admin_auth_headers)
    assert reschedule.status_code == 409


def test_scheduler_publishes_due_posts_exactly_once(client: TestClient, admin_auth_headers, db_session):
    before = _count(client, admin_auth_headers)
    due = _schedule(client, admin_auth_headers, "sched-due")
    later = _schedule(client, admin_auth_headers, "sched-later", days=2)

    # Pretend the server was down and the time passed.
    db_session.query(Post).filter(Post.post_id == due["post_id"]).update(
        {Post.scheduled_at: datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)}
    )
    db_session.commit()

    assert PostService.publish_due_posts(db_session) >= 1
    assert PostService.publish_due_posts(db_session) == 0  # nothing double-published

    feed = _feed_ids(client, admin_auth_headers)
    assert due["post_id"] in feed and later["post_id"] not in feed
    assert _count(client, admin_auth_headers) == before + 1


def test_late_publish_appears_at_top_of_feed(client: TestClient, admin_auth_headers):
    early = _schedule(client, admin_auth_headers, "sched-order-early")      # lower id
    newer = _create(client, admin_auth_headers, post_type="text", content="sched-order-newer").json()["items"][0]
    client.post(f"/api/v1/posts/{early['post_id']}/publish", headers=admin_auth_headers)
    ids = _feed_ids(client, admin_auth_headers)
    assert ids.index(early["post_id"]) < ids.index(newer["post_id"])


def test_feed_pagination_follows_publish_order(client: TestClient, admin_auth_headers):
    for i in range(3):
        _create(client, admin_auth_headers, post_type="text", content=f"sched-page-{i}")
    first = client.get("/api/v1/posts?limit=2", headers=admin_auth_headers).json()
    assert first["has_more"] is True and first["next_before_id"] == first["items"][-1]["post_id"]
    second = client.get(f"/api/v1/posts?limit=2&before_id={first['next_before_id']}", headers=admin_auth_headers).json()
    assert not {p["post_id"] for p in first["items"]} & {p["post_id"] for p in second["items"]}


def test_cancel_scheduled_post(client: TestClient, admin_auth_headers):
    before = _count(client, admin_auth_headers)
    post = _schedule(client, admin_auth_headers, "sched-cancel")
    r = client.delete(f"/api/v1/posts/{post['post_id']}", headers=admin_auth_headers)
    assert r.status_code == 200
    assert _count(client, admin_auth_headers) == before  # was never counted
    listed = client.get("/api/v1/posts/scheduled?limit=100", headers=admin_auth_headers).json()
    assert all(p["post_id"] != post["post_id"] for p in listed["items"])


def test_deleting_published_post_lowers_count(client: TestClient, admin_auth_headers):
    post = _create(client, admin_auth_headers, post_type="text", content="sched-del").json()["items"][0]
    mid = _count(client, admin_auth_headers)
    assert client.delete(f"/api/v1/posts/{post['post_id']}", headers=admin_auth_headers).status_code == 200
    assert _count(client, admin_auth_headers) == mid - 1


def test_scheduled_media_only_for_admin(client: TestClient, admin_auth_headers, influencer_auth_headers):
    r = _create(client, admin_auth_headers, post_type="image", content="sched-img",
                scheduled_at=_when(hours=2), files={"media": ("a.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    url = r.json()["items"][0]["media_url"]
    assert client.get(url).status_code == 404
    assert client.get(url, headers=influencer_auth_headers).status_code == 404
    ok = client.get(url, headers=admin_auth_headers)
    assert ok.status_code == 200 and ok.content == PNG
    assert ok.headers["cache-control"] == "private, no-store"


def test_cannot_vote_in_scheduled_poll(client: TestClient, admin_auth_headers, influencer_auth_headers):
    r = _create(client, admin_auth_headers, post_type="poll", content="sched-poll?",
                poll_options='["a","b"]', scheduled_at=_when(hours=2))
    assert r.status_code == 201, r.text
    post = r.json()["items"][0]
    option_id = post["poll"]["options"][0]["option_id"]
    vote = client.post(f"/api/v1/posts/{post['post_id']}/vote", json={"option_id": option_id},
                       headers=influencer_auth_headers)
    assert vote.status_code == 404


def test_scheduled_list_filters(client: TestClient, admin_auth_headers):
    soon = _schedule(client, admin_auth_headers, "sched-filter-soon", days=10)
    far = _schedule(client, admin_auth_headers, "sched-filter-far", days=20)
    start = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat(timespec="seconds")
    r = client.get("/api/v1/posts/scheduled", params={"from_at": start}, headers=admin_auth_headers).json()
    ids = [p["post_id"] for p in r["items"]]
    assert far["post_id"] in ids and soon["post_id"] not in ids
    naive = client.get("/api/v1/posts/scheduled", params={"from_at": "2030-01-01T00:00:00"}, headers=admin_auth_headers)
    assert naive.status_code == 400
    swapped = client.get("/api/v1/posts/scheduled",
                         params={"from_at": _when(days=2), "to_at": _when(days=1)}, headers=admin_auth_headers)
    assert swapped.status_code == 400