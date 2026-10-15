from starlette.testclient import TestClient
from app.common.models.story import StoryReport

def test_report_story_with_reason_and_details(
    client: TestClient,
    creator_auth_headers: dict,
    admin_auth_headers: dict,
    db_session,
):
    # 1. Creator creates a story
    story_payload = {
        "media_url": "https://example.com/test-story.jpg",
        "media_type": "image",
        "caption": "Story for report test",
        "duration_hours": 24,
    }
    story_res = client.post("/api/v1/stories", json=story_payload, headers=creator_auth_headers)
    assert story_res.status_code == 201
    story_id = story_res.json()["id"]

    # 2. User reports story with reason and details
    report_payload = {
        "reason": "Harassment or bullying",
        "details": "This story contains inappropriate harassment targeting individuals.",
    }
    report_res = client.post(
        f"/api/v1/stories/{story_id}/report",
        json=report_payload,
        headers=admin_auth_headers,
    )
    assert report_res.status_code == 200
    assert report_res.json()["success"] is True

    # 3. Verify in database
    db_report = db_session.query(StoryReport).filter(StoryReport.story_id == story_id).first()
    assert db_report is not None
    assert db_report.reason == "Harassment or bullying"
    assert db_report.details == "This story contains inappropriate harassment targeting individuals."

    # 4. Admin fetches story reports endpoint
    admin_reports_res = client.get("/api/v1/admin/stories/reports", headers=admin_auth_headers)
    assert admin_reports_res.status_code == 200
    reports_list = admin_reports_res.json()
    assert len(reports_list) >= 1

    matched_report = next((r for r in reports_list if r["story_id"] == story_id), None)
    assert matched_report is not None
    assert matched_report["reason"] == "Harassment or bullying"
    assert matched_report["details"] == "This story contains inappropriate harassment targeting individuals."
    assert matched_report["story"] is not None
    assert matched_report["story"]["story_id"] == story_id

    # 5. Admin sends warning to creator
    creator_user_id = matched_report["story"]["user_id"]
    warn_res = client.post(
        f"/api/v1/admin/stories/{story_id}/warn",
        json={"message": "Please do not post harassing content. This is your first warning."},
        headers=admin_auth_headers,
    )
    assert warn_res.status_code == 200
    warn_data = warn_res.json()
    assert warn_data["success"] is True
    assert warn_data["story_id"] == story_id
    assert warn_data["user_id"] == creator_user_id

    # 6. Admin suspends (bans) user
    ban_res = client.post(f"/api/v1/admin/users/{creator_user_id}/ban", headers=admin_auth_headers)
    assert ban_res.status_code == 200
    assert ban_res.json()["success"] is True

    # 7. Admin unsuspends (unbans) user
    unban_res = client.post(f"/api/v1/admin/users/{creator_user_id}/unban", headers=admin_auth_headers)
    assert unban_res.status_code == 200
    assert unban_res.json()["success"] is True

    # 8. Admin deletes story
    del_res = client.delete(f"/api/v1/admin/stories/{story_id}", headers=admin_auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 9. Admin restores story
    res_res = client.patch(f"/api/v1/admin/stories/{story_id}/restore", headers=admin_auth_headers)
    assert res_res.status_code == 200
    assert res_res.json()["success"] is True