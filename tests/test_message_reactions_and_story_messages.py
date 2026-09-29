"""Story replies/reactions arrive as chat messages, and messages can be reacted to."""
from datetime import timedelta

import pytest

from app.common.models.messaging import DirectMessage, MessageReaction
from app.common.models.story import Story, StoryLike, StoryReply
from app.common.models.user import User
from app.core.security import create_access_token
from app.utils.seed import seed_db_data  # noqa: F401  (session fixture seeds users)

API = "/api/v1"


def _h(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid)}"}


@pytest.fixture
def people(db_session):
    users = db_session.query(User).order_by(User.user_id).all()
    assert len(users) >= 3
    return users[0].user_id, users[1].user_id, users[2].user_id


@pytest.fixture
def story(db_session, people):
    from app.common.services.story_service import make_naive, utc_now

    owner, _, _ = people
    s = Story(
        user_id=owner,
        media_url="gradient:insta",
        media_type="text",
        caption="Vanakkam from Madurai",
        expires_at=make_naive(utc_now()) + timedelta(hours=24),
        audience="PUBLIC",
    )
    db_session.add(s)
    db_session.commit()
    yield s.story_id
    db_session.query(DirectMessage).filter(DirectMessage.story_id == s.story_id).delete()
    db_session.query(StoryReply).filter(StoryReply.story_id == s.story_id).delete()
    db_session.query(StoryLike).filter(StoryLike.story_id == s.story_id).delete()
    db_session.query(Story).filter(Story.story_id == s.story_id).delete()
    db_session.commit()


def _thread(client, viewer, other, **params):
    r = client.get(f"{API}/messages/thread/{other}", params=params, headers=_h(viewer))
    assert r.status_code == 200, r.text
    return r.json()


def test_story_reply_becomes_a_message(client, people, story):
    owner, replier, _ = people
    r = client.post(f"{API}/stories/{story}/reply", json={"text": "Superb!"}, headers=_h(replier))
    assert r.status_code == 201, r.text

    msgs = _thread(client, owner, replier)["messages"]
    m = next(x for x in msgs if x["kind"] == "story_reply")
    assert m["body"] == "Superb!"
    assert m["is_mine"] is False and m["sender_id"] == replier
    assert m["story"]["story_id"] == story
    assert m["story"]["caption"] == "Vanakkam from Madurai"
    assert m["story"]["available"] is True

    # It shows up in the inbox preview for the owner, flagged with its kind.
    convs = client.get(f"{API}/messages/conversations", headers=_h(owner)).json()
    last = next(c for c in convs if c["partner"]["user_id"] == replier)["last_message"]
    assert last["kind"] == "story_reply" and last["body"] == "Superb!"


def test_replying_to_own_story_sends_no_message(client, db_session, people, story):
    owner, _, _ = people
    before = db_session.query(DirectMessage).count()
    r = client.post(f"{API}/stories/{story}/reply", json={"text": "note to self"}, headers=_h(owner))
    assert r.status_code == 201
    assert db_session.query(DirectMessage).count() == before


def test_story_react_persists_and_sends_one_message_per_emoji(client, db_session, people, story):
    owner, reactor, _ = people
    for _ in range(3):  # repeated taps of the same emoji
        r = client.post(f"{API}/stories/{story}/react", json={"emoji": "🔥"}, headers=_h(reactor))
        assert r.status_code == 200, r.text
    # First-ever react used to be rolled back (missing commit); it must persist now.
    assert db_session.query(StoryLike).filter_by(story_id=story, user_id=reactor).count() == 1

    client.post(f"{API}/stories/{story}/react", json={"emoji": "😍"}, headers=_h(reactor))

    msgs = [m for m in _thread(client, owner, reactor)["messages"] if m["kind"] == "story_reaction"]
    assert [m["body"] for m in msgs] == ["🔥", "😍"]


def test_story_like_sends_heart_message_once(client, people, story):
    owner, liker, _ = people
    client.post(f"{API}/stories/{story}/like", headers=_h(liker))
    client.delete(f"{API}/stories/{story}/like", headers=_h(liker))
    client.post(f"{API}/stories/{story}/like", headers=_h(liker))
    msgs = [m for m in _thread(client, owner, liker)["messages"] if m["kind"] == "story_reaction"]
    assert len(msgs) == 1 and msgs[0]["body"] == "\u2764\ufe0f"


def test_expired_story_context_is_marked_unavailable(client, db_session, people, story):
    owner, replier, _ = people
    client.post(f"{API}/stories/{story}/reply", json={"text": "hey"}, headers=_h(replier))
    from app.common.services.story_service import make_naive, utc_now

    s = db_session.get(Story, story)
    s.expires_at = make_naive(utc_now()) - timedelta(minutes=1)
    db_session.commit()
    m = next(x for x in _thread(client, owner, replier)["messages"] if x["kind"] == "story_reply")
    assert m["story"]["available"] is False


def test_react_to_sent_and_received_messages(client, db_session, people):
    a, b, _ = people
    sent = client.post(f"{API}/messages/thread/{b}", json={"body": "hello"}, headers=_h(a)).json()
    mid = sent["id"]

    # The receiver reacts, then the sender reacts to their own message too.
    r = client.put(f"{API}/messages/{mid}/reaction", json={"emoji": "😂"}, headers=_h(b))
    assert r.status_code == 200, r.text
    client.put(f"{API}/messages/{mid}/reaction", json={"emoji": "❤️"}, headers=_h(a))

    m = next(x for x in _thread(client, a, b)["messages"] if x["id"] == mid)
    assert {(x["user_id"], x["emoji"]) for x in m["reactions"]} == {(b, "😂"), (a, "❤️")}

    # Reacting again replaces rather than stacks.
    r = client.put(f"{API}/messages/{mid}/reaction", json={"emoji": "👍"}, headers=_h(b))
    assert {x["emoji"] for x in r.json()["reactions"]} == {"👍", "❤️"}
    assert db_session.query(MessageReaction).filter_by(message_id=mid, user_id=b).count() == 1

    # Removing works and is idempotent.
    r = client.delete(f"{API}/messages/{mid}/reaction", headers=_h(b))
    assert [x["emoji"] for x in r.json()["reactions"]] == ["❤️"]
    assert client.delete(f"{API}/messages/{mid}/reaction", headers=_h(b)).status_code == 200


def test_reaction_changes_reach_the_other_person_via_sync(client, people):
    a, b, _ = people
    first = client.post(f"{API}/messages/thread/{b}", json={"body": "one"}, headers=_h(a)).json()
    second = client.post(f"{API}/messages/thread/{b}", json={"body": "two"}, headers=_h(a)).json()
    client.put(f"{API}/messages/{first['id']}/reaction", json={"emoji": "🙏"}, headers=_h(b))

    # A poll that asks only for messages newer than `second` still learns about the reaction.
    poll = _thread(client, a, b, after_id=second["id"], sync_from_id=first["id"])
    assert poll["messages"] == []
    assert poll["reactions_sync"][str(first["id"])] == [{"user_id": b, "emoji": "🙏"}]
    assert poll["reactions_sync"][str(second["id"])] == []

    client.delete(f"{API}/messages/{first['id']}/reaction", headers=_h(b))
    poll = _thread(client, a, b, after_id=second["id"], sync_from_id=first["id"])
    assert poll["reactions_sync"][str(first["id"])] == []


def test_cannot_react_to_someone_elses_chat(client, people):
    a, b, c = people
    mid = client.post(f"{API}/messages/thread/{b}", json={"body": "private"}, headers=_h(a)).json()["id"]
    assert client.put(f"{API}/messages/{mid}/reaction", json={"emoji": "👍"}, headers=_h(c)).status_code == 404
    assert client.delete(f"{API}/messages/{mid}/reaction", headers=_h(c)).status_code == 404
    assert client.put(f"{API}/messages/999999/reaction", json={"emoji": "👍"}, headers=_h(a)).status_code == 404


@pytest.mark.parametrize("bad", ["", "   ", "hi", "a👍"])
def test_reaction_must_be_an_emoji(client, people, bad):
    a, b, _ = people
    mid = client.post(f"{API}/messages/thread/{b}", json={"body": "x"}, headers=_h(a)).json()["id"]
    assert client.put(f"{API}/messages/{mid}/reaction", json={"emoji": bad}, headers=_h(b)).status_code == 422


def test_reactions_require_login(client):
    assert client.put(f"{API}/messages/1/reaction", json={"emoji": "👍"}).status_code == 401