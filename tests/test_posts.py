import json

from fastapi.testclient import TestClient

# Smallest valid files, built from real file signatures.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
HTML_AS_PNG = b"<html><script>alert(1)</script></html>"


def _create(client, headers, **data):
    files = data.pop("files", None)
    return client.post("/api/v1/posts", data=data, files=files, headers=headers)


def test_text_post_saved_and_listed(client: TestClient, admin_auth_headers: dict):
    r = _create(client, admin_auth_headers, post_type="text", content="வணக்கம் Tamila #Chennai")
    assert r.status_code == 201, r.text
    body = r.json()
    post = body["items"][0]
    assert post["post_type"] == "text"
    assert post["content"] == "வணக்கம் Tamila #Chennai"
    assert post["created_at"].endswith("Z")
    assert post["can_delete"] is True
    assert str(post["author_id"]) in body["authors"]

    feed = client.get("/api/v1/posts", headers=admin_auth_headers).json()
    assert any(p["post_id"] == post["post_id"] for p in feed["items"])


def test_only_admin_can_post(client: TestClient, creator_auth_headers, influencer_auth_headers, freelancer_auth_headers):
    for h in (influencer_auth_headers, freelancer_auth_headers):
        r = _create(client, h, post_type="text", content="hello")
        assert r.status_code == 403
    # but everyone can read
    assert client.get("/api/v1/posts", headers=influencer_auth_headers).status_code == 200


def test_requires_login(client: TestClient):
    assert client.post("/api/v1/posts", data={"post_type": "text", "content": "x"}).status_code == 401
    assert client.get("/api/v1/posts").status_code == 401


def test_empty_text_rejected(client: TestClient, admin_auth_headers):
    assert _create(client, admin_auth_headers, post_type="text", content="   ").status_code == 400


def test_image_post_and_media_endpoint(client: TestClient, admin_auth_headers):
    r = _create(client, admin_auth_headers, post_type="image", content="caption",
                files={"media": ("a.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    post = r.json()["items"][0]
    assert post["media_type"] == "image" and post["media_url"].endswith("/media")
    # feed JSON must not carry the file itself
    assert "media_data" not in json.dumps(post)

    m = client.get(post["media_url"])  # public, no auth header
    assert m.status_code == 200
    assert m.headers["content-type"] == "image/png"
    assert m.content == PNG


def test_image_slot_rejects_video_and_fake_files(client: TestClient, admin_auth_headers):
    r = _create(client, admin_auth_headers, post_type="image", files={"media": ("v.mp4", MP4, "video/mp4")})
    assert r.status_code == 400
    r = _create(client, admin_auth_headers, post_type="image", files={"media": ("x.png", HTML_AS_PNG, "image/png")})
    assert r.status_code == 400
    r = _create(client, admin_auth_headers, post_type="video", files={"media": ("a.png", PNG, "video/mp4")})
    assert r.status_code == 400
    assert _create(client, admin_auth_headers, post_type="image").status_code == 400


def test_video_post_with_range_request(client: TestClient, admin_auth_headers):
    r = _create(client, admin_auth_headers, post_type="video", files={"media": ("v.mp4", MP4, "video/mp4")})
    assert r.status_code == 201, r.text
    url = r.json()["items"][0]["media_url"]
    part = client.get(url, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206
    assert part.content == MP4[:10]
    assert part.headers["content-range"] == f"bytes 0-9/{len(MP4)}"
    tail = client.get(url, headers={"Range": "bytes=-4"})
    assert tail.status_code == 206 and tail.content == MP4[-4:]
    assert client.get(url, headers={"Range": "bytes=9999-"}).status_code == 416


def test_gif_post_host_allowlist(client: TestClient, admin_auth_headers):
    ok = _create(client, admin_auth_headers, post_type="gif", gif_url="https://media.giphy.com/media/abc/giphy.gif")
    assert ok.status_code == 201
    assert ok.json()["items"][0]["gif_url"].startswith("https://media.giphy.com/")
    for bad in ("http://media.giphy.com/a.gif", "https://evil.com/a.gif", "https://giphy.com.evil.com/a.gif", ""):
        assert _create(client, admin_auth_headers, post_type="gif", gif_url=bad).status_code == 400


def test_poll_create_vote_once(client: TestClient, admin_auth_headers, influencer_auth_headers):
    r = _create(client, admin_auth_headers, post_type="poll", content="Best tool?",
                poll_options=json.dumps(["Caption", "Voice", "Poster"]))
    assert r.status_code == 201, r.text
    post = r.json()["items"][0]
    opts = post["poll"]["options"]
    assert [o["text"] for o in opts] == ["Caption", "Voice", "Poster"]
    assert post["poll"]["total_votes"] == 0 and post["poll"]["my_vote_option_id"] is None

    v = client.post(f"/api/v1/posts/{post['post_id']}/vote", json={"option_id": opts[1]["option_id"]},
                    headers=influencer_auth_headers)
    assert v.status_code == 200
    assert v.json()["total_votes"] == 1 and v.json()["my_vote_option_id"] == opts[1]["option_id"]

    again = client.post(f"/api/v1/posts/{post['post_id']}/vote", json={"option_id": opts[0]["option_id"]},
                        headers=influencer_auth_headers)
    assert again.status_code == 409

    # admin's own view: has not voted; influencer's view shows their vote
    feed_a = client.get("/api/v1/posts", headers=admin_auth_headers).json()["items"][0]["poll"]
    assert feed_a["my_vote_option_id"] is None and feed_a["total_votes"] == 1
    feed_i = client.get("/api/v1/posts", headers=influencer_auth_headers).json()["items"][0]["poll"]
    assert feed_i["my_vote_option_id"] == opts[1]["option_id"]


def test_poll_validation(client: TestClient, admin_auth_headers):
    def poll(q, opts):
        return _create(client, admin_auth_headers, post_type="poll", content=q, poll_options=json.dumps(opts))
    assert poll("Q?", ["only one"]).status_code == 400
    assert poll("Q?", ["a", "A"]).status_code == 400
    assert poll("Q?", ["1", "2", "3", "4", "5", "6"]).status_code == 400
    assert poll("", ["a", "b"]).status_code == 400
    assert poll("Q?", ["x" * 81, "b"]).status_code == 400
    assert poll("Q?", ["a", "b"]).status_code == 201


def test_vote_with_foreign_option_rejected(client: TestClient, admin_auth_headers):
    p1 = _create(client, admin_auth_headers, post_type="poll", content="One?", poll_options=json.dumps(["a", "b"])).json()["items"][0]
    p2 = _create(client, admin_auth_headers, post_type="poll", content="Two?", poll_options=json.dumps(["c", "d"])).json()["items"][0]
    r = client.post(f"/api/v1/posts/{p1['post_id']}/vote", json={"option_id": p2["poll"]["options"][0]["option_id"]},
                    headers=admin_auth_headers)
    assert r.status_code == 400


def test_delete_rules_and_pagination(client: TestClient, admin_auth_headers, influencer_auth_headers):
    ids = [
        _create(client, admin_auth_headers, post_type="text", content=f"post {i}").json()["items"][0]["post_id"]
        for i in range(3)
    ]
    page1 = client.get("/api/v1/posts?limit=2", headers=admin_auth_headers).json()
    assert len(page1["items"]) == 2 and page1["has_more"] is True
    assert page1["items"][0]["post_id"] == ids[-1]
    page2 = client.get(f"/api/v1/posts?limit=2&before_id={page1['next_before_id']}", headers=admin_auth_headers).json()
    assert page2["items"][0]["post_id"] < page1["items"][-1]["post_id"]

    # a non-owner, non-admin cannot delete; viewers don't get the delete flag
    assert client.delete(f"/api/v1/posts/{ids[0]}", headers=influencer_auth_headers).status_code == 403
    flags = {p["post_id"]: p["can_delete"] for p in client.get("/api/v1/posts?limit=30", headers=influencer_auth_headers).json()["items"]}
    assert flags[ids[0]] is False

    assert client.delete(f"/api/v1/posts/{ids[0]}", headers=admin_auth_headers).status_code == 200
    assert client.delete(f"/api/v1/posts/{ids[0]}", headers=admin_auth_headers).status_code == 404


def test_posts_count_follows_create_and_delete(client: TestClient, admin_auth_headers, db_session):
    from app.common.models.user import User
    before = db_session.get(User, 1)
    db_session.refresh(before)
    start = before.profile.posts_count if before.profile else 0
    pid = _create(client, admin_auth_headers, post_type="text", content="count me").json()["items"][0]["post_id"]
    db_session.expire_all()
    assert db_session.get(User, 1).profile.posts_count == start + 1
    client.delete(f"/api/v1/posts/{pid}", headers=admin_auth_headers)
    db_session.expire_all()
    assert db_session.get(User, 1).profile.posts_count == start
