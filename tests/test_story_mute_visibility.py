import pytest
from starlette.testclient import TestClient

def test_mute_creator_hides_stories_until_unmute(
    client: TestClient,
    influencer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session,
):
    # Influencer posts a story
    create_resp = client.post(
        "/api/v1/stories",
        json={"content": "Story by Influencer", "audience": "PUBLIC"},
        headers=influencer_auth_headers,
    )
    assert create_resp.status_code in (200, 201)
    influencer_id = create_resp.json()["user_id"]

    # Freelancer checks feed before mute - story is visible
    feed_before = client.get("/api/v1/stories", headers=freelancer_auth_headers).json()
    inf_before = [g for g in feed_before if g["id"] == influencer_id]
    assert len(inf_before) > 0

    # Freelancer mutes Influencer
    mute_resp = client.post(f"/api/v1/stories/mute/{influencer_id}", headers=freelancer_auth_headers)
    assert mute_resp.status_code == 200
    assert mute_resp.json()["is_muted"] is True

    # Freelancer checks feed after mute - Influencer stories MUST NOT appear
    feed_after = client.get("/api/v1/stories", headers=freelancer_auth_headers).json()
    inf_after = [g for g in feed_after if g["id"] == influencer_id]
    assert len(inf_after) == 0

    # Freelancer checks get_user_stories for Influencer - MUST return empty list
    user_stories = client.get(f"/api/v1/stories/user/{influencer_id}", headers=freelancer_auth_headers).json()
    assert len(user_stories) == 0

    # Freelancer un-mutes Influencer
    unmute_resp = client.delete(f"/api/v1/stories/mute/{influencer_id}", headers=freelancer_auth_headers)
    assert unmute_resp.status_code == 200
    assert unmute_resp.json()["is_muted"] is False

    # Freelancer checks feed after unmute - Influencer stories reappear
    feed_restored = client.get("/api/v1/stories", headers=freelancer_auth_headers).json()
    inf_restored = [g for g in feed_restored if g["id"] == influencer_id]
    assert len(inf_restored) > 0
