import pytest
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
    story_res = client.post("/api/stories", json=story_payload, headers=creator_auth_headers)
    assert story_res.status_code == 201
    story_id = story_res.json()["id"]

    # 2. User reports story with reason and details
    report_payload = {
        "reason": "Harassment or bullying",
        "details": "This story contains inappropriate harassment targeting individuals.",
    }
    report_res = client.post(
        f"/api/stories/{story_id}/report",
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
    admin_reports_res = client.get("/api/admin/stories/reports", headers=admin_auth_headers)
    assert admin_reports_res.status_code == 200
    reports_list = admin_reports_res.json()
    assert len(reports_list) >= 1

    matched_report = next((r for r in reports_list if r["story_id"] == story_id), None)
    assert matched_report is not None
    assert matched_report["reason"] == "Harassment or bullying"
    assert matched_report["details"] == "This story contains inappropriate harassment targeting individuals."
    assert matched_report["story"] is not None
    assert matched_report["story"]["story_id"] == story_id
