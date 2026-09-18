from fastapi.testclient import TestClient


def test_admin_endpoints(client: TestClient, admin_auth_headers: dict, creator_auth_headers: dict):
    # Admin overview
    resp = client.get("/api/admin/overview", headers=admin_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "total_stories" in data

    # Non-admin forbidden
    creator_resp = client.get("/api/admin/overview", headers=creator_auth_headers)
    assert creator_resp.status_code == 403
