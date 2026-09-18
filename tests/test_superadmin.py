from fastapi.testclient import TestClient


def test_superadmin_endpoints(client: TestClient):
    resp = client.get("/api/superadmin/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
