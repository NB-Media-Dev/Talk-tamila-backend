from fastapi.testclient import TestClient

from app.core.security import create_access_token

FREELANCER_ID = 11  # "free@talktamila.com" in the seed data
INFLUENCER_ID = 3


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_freelancer_stats_requires_freelancer(client: TestClient):
    ok = client.get("/api/v1/freelancer/stats", headers=_auth(FREELANCER_ID))
    assert ok.status_code == 200
    assert ok.json()["role"] == "freelancer"
    assert client.get("/api/v1/freelancer/stats", headers=_auth(INFLUENCER_ID)).status_code == 403
    assert client.get("/api/v1/freelancer/stats").status_code == 401