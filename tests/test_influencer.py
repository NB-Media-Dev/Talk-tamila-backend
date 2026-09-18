from fastapi.testclient import TestClient


def test_influencer_endpoints(client: TestClient, creator_auth_headers: dict):
    # Influencer stats
    resp = client.get("/api/influencer/stats", headers=creator_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "active_stories_count" in data
    assert "total_views" in data
    assert "total_likes" in data

    # Unauthenticated forbidden
    unauth_resp = client.get("/api/influencer/stats")
    assert unauth_resp.status_code == 401
