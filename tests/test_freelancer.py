from fastapi.testclient import TestClient


def test_freelancer_endpoints(client: TestClient):
    resp = client.get("/api/freelancer/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
