from app.core.security import create_access_token

def h(uid): return {"Authorization": f"Bearer {create_access_token(uid)}"}

def test_public_profile_and_follow(client):
    me = client.get("/api/v1/auth/profile", headers=h(1)).json()
    other = client.get("/api/v1/auth/profile", headers=h(3)).json()
    r = client.get(f"/api/v1/users/by-username/{other['username']}", headers=h(1))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user_id"] == 3 and d["is_me"] is False and d["is_following"] is False
    assert "email" not in d and "mobile_no" not in d and "dob" not in d
    # case-insensitive + @ prefix
    assert client.get(f"/api/v1/users/by-username/@{other['username'].upper()}", headers=h(1)).status_code == 200
    # own profile flagged
    assert client.get(f"/api/v1/users/by-username/{me['username']}", headers=h(1)).json()["is_me"] is True
    # follow then re-check, and 'follows_you' from the other side
    assert client.post("/api/v1/stories/follow/3", headers=h(1)).status_code == 200
    d = client.get(f"/api/v1/users/by-username/{other['username']}", headers=h(1)).json()
    assert d["is_following"] is True and d["followers_count"] == 1
    d2 = client.get(f"/api/v1/users/by-username/{me['username']}", headers=h(3)).json()
    assert d2["follows_you"] is True and d2["following_count"] == 1 and d2["followers_count"] == 0
    assert client.get("/api/v1/auth/profile", headers=h(3)).json()["followers_count"] == 1
    assert client.get("/api/v1/users/by-username/nobody_here_x", headers=h(1)).status_code == 404

def test_unsend(client):
    sent = client.post("/api/v1/messages/thread/1", json={"body": "hello"}, headers=h(3))
    assert sent.status_code == 201, sent.text
    mid = sent.json()["id"]
    # reaction from the receiver, to be cleaned up on unsend
    assert client.put(f"/api/v1/messages/{mid}/reaction", json={"emoji": "❤️"}, headers=h(1)).status_code == 200
    # receiver cannot unsend the sender's message; a stranger gets 404
    assert client.delete(f"/api/v1/messages/{mid}", headers=h(1)).status_code == 403
    assert client.delete(f"/api/v1/messages/{mid}", headers=h(4)).status_code == 404
    # thread poll reports the id as existing
    t = client.get("/api/v1/messages/thread/3", params={"after_id": mid, "sync_from_id": mid}, headers=h(1)).json()
    assert t["existing_ids"] == [mid]
    # sender unsends
    assert client.delete(f"/api/v1/messages/{mid}", headers=h(3)).json() == {"success": True, "message_id": mid}
    t = client.get("/api/v1/messages/thread/3", params={"after_id": 0, "sync_from_id": mid}, headers=h(1)).json()
    assert t["existing_ids"] == [] and t["messages"] == []
    # first-page load has no existing_ids
    assert client.get("/api/v1/messages/thread/3", headers=h(1)).json()["existing_ids"] is None
    assert client.delete(f"/api/v1/messages/{mid}", headers=h(3)).status_code == 404
    