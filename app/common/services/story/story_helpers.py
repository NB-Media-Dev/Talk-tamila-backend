"""Shared story helpers: time formatting, mention parsing, and building story response items."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.common.models.social import Notification
from app.common.models.moderation import UserBlock
from app.common.models.story import (
    Story,
    StoryLike,
    StoryMention,
    StoryReply,
    StoryShare,
    StoryView,
)
from app.common.models.user import User
from app.common.schemas.story import (
    StoryItemResponse,
    StoryMentionItem,
    StorySlideResponse,
    StoryUserResponse,
)

DEFAULT_DURATION_HOURS = 24


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def make_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def get_time_ago(dt: Optional[datetime]) -> str:
    if not dt:
        return "Just now"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = max(0, int(diff.total_seconds()))
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def fetch_batch_story_stats(story_ids: List[int], current_user_id: Optional[int], db: Session) -> Dict[str, Any]:
    if not story_ids:
        return {
            "views": {},
            "likes": {},
            "replies": {},
            "shares": {},
            "viewed_by_me": set(),
            "liked_by_me": set(),
        }

    views_rows = db.query(StoryView.story_id, func.count(func.distinct(StoryView.user_id))).filter(StoryView.story_id.in_(story_ids)).group_by(StoryView.story_id).all()
    likes_rows = db.query(StoryLike.story_id, func.count(func.distinct(StoryLike.user_id))).filter(StoryLike.story_id.in_(story_ids)).group_by(StoryLike.story_id).all()
    replies_rows = db.query(StoryReply.story_id, func.count(StoryReply.reply_id)).filter(StoryReply.story_id.in_(story_ids)).group_by(StoryReply.story_id).all()
    shares_rows = db.query(StoryShare.story_id, func.count(StoryShare.share_id)).filter(StoryShare.story_id.in_(story_ids)).group_by(StoryShare.story_id).all()

    viewed_by_me = set()
    liked_by_me = set()
    if current_user_id:
        v_rows = db.query(StoryView.story_id).filter(StoryView.story_id.in_(story_ids), StoryView.user_id == current_user_id).all()
        viewed_by_me = {r[0] for r in v_rows}
        l_rows = db.query(StoryLike.story_id).filter(StoryLike.story_id.in_(story_ids), StoryLike.user_id == current_user_id).all()
        liked_by_me = {r[0] for r in l_rows}

    return {
        "views": {r[0]: r[1] for r in views_rows},
        "likes": {r[0]: r[1] for r in likes_rows},
        "replies": {r[0]: r[1] for r in replies_rows},
        "shares": {r[0]: r[1] for r in shares_rows},
        "viewed_by_me": viewed_by_me,
        "liked_by_me": liked_by_me,
    }


def extract_mentioned_usernames(text: Optional[str]) -> List[str]:
    if not text:
        return []
    matches = re.findall(r"@([a-zA-Z0-9_]+)", text)
    seen = set()
    result = []
    for m in matches:
        low = m.lower()
        if low not in seen:
            seen.add(low)
            result.append(m)
    return result


def process_and_create_mentions(
    db: Session,
    story: Story,
    mentions_payload: Optional[List[Any]],
    caption: Optional[str],
    current_user: User,
) -> List[StoryMention]:
    candidate_user_ids = set()
    candidate_usernames = set()
    coords_by_uid = {}
    coords_by_uname = {}

    if mentions_payload:
        for m in mentions_payload:
            uid = getattr(m, "user_id", None) if hasattr(m, "user_id") else (m.get("user_id") if isinstance(m, dict) else None)
            uname = getattr(m, "username", None) if hasattr(m, "username") else (m.get("username") if isinstance(m, dict) else None)
            x = getattr(m, "x", None) if hasattr(m, "x") else (m.get("x") if isinstance(m, dict) else None)
            y = getattr(m, "y", None) if hasattr(m, "y") else (m.get("y") if isinstance(m, dict) else None)
            if uid:
                candidate_user_ids.add(int(uid))
                coords_by_uid[int(uid)] = (x, y)
            if uname:
                clean_uname = uname.strip().lstrip("@").lower()
                candidate_usernames.add(clean_uname)
                coords_by_uname[clean_uname] = (x, y)

    caption_unames = extract_mentioned_usernames(caption)
    for u in caption_unames:
        candidate_usernames.add(u.strip().lstrip("@").lower())

    if not candidate_user_ids and not candidate_usernames:
        return []

    query_conds = []
    if candidate_user_ids:
        query_conds.append(User.user_id.in_(list(candidate_user_ids)))
    if candidate_usernames:
        query_conds.append(func.lower(User.username).in_(list(candidate_usernames)))

    target_users = db.query(User).filter(or_(*query_conds), User.is_active.is_(True)).all()
    created_mentions = []

    for target in target_users:
        # Check blocking
        is_blocked = db.query(UserBlock).filter(
            or_(
                and_(UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == target.user_id),
                and_(UserBlock.blocker_id == target.user_id, UserBlock.blocked_id == current_user.id),
            )
        ).first() is not None

        if is_blocked:
            if mentions_payload:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot mention @{target.username}: user is blocked."
                )
            continue

        x, y = coords_by_uid.get(target.user_id, coords_by_uname.get((target.username or "").lower(), (None, None)))

        existing = db.query(StoryMention).filter(
            StoryMention.story_id == story.story_id,
            StoryMention.mentioned_user_id == target.user_id,
        ).first()

        if not existing:
            mention = StoryMention(
                story_id=story.story_id,
                mentioned_user_id=target.user_id,
                created_by_user_id=current_user.id,
                owner_user_id=current_user.id,
                x=x,
                y=y,
                created_at=make_naive(utc_now()),
            )
            db.add(mention)
            created_mentions.append(mention)

            # Send Notification ONLY to mentioned user (STORY_MENTION)
            if target.user_id != current_user.id:
                notif = Notification(
                    user_id=target.user_id,
                    type="STORY_MENTION",
                    message=f"{current_user.username} mentioned you in their story",
                    reference_id=story.story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
                db.add(notif)

    db.commit()
    return created_mentions


def is_story_root_active(s: Story, db: Session, now_naive: datetime) -> bool:
    if not s.original_story_id or s.original_story_id == s.story_id:
        return True
    root = s.original_story or db.get(Story, s.original_story_id)
    if not root or root.is_deleted or (root.expires_at and root.expires_at <= now_naive):
        return False
    return True


def build_story_item(
    story: Story,
    current_user_id: Optional[int],
    db: Session,
    batch_stats: Optional[Dict[str, Any]] = None,
) -> StoryItemResponse:
    if batch_stats is not None:
        views_count = batch_stats["views"].get(story.story_id, 0)
        likes_count = batch_stats["likes"].get(story.story_id, 0)
        replies_count = batch_stats["replies"].get(story.story_id, 0)
        shares_count = batch_stats["shares"].get(story.story_id, 0)
        viewed_by_me = story.story_id in batch_stats["viewed_by_me"]
        liked_by_me = story.story_id in batch_stats["liked_by_me"]
    else:
        views_count = db.query(func.count(func.distinct(StoryView.user_id))).filter(StoryView.story_id == story.story_id).scalar() or 0
        likes_count = db.query(func.count(func.distinct(StoryLike.user_id))).filter(StoryLike.story_id == story.story_id).scalar() or 0
        replies_count = db.query(func.count(StoryReply.reply_id)).filter(StoryReply.story_id == story.story_id).scalar() or 0
        shares_count = db.query(func.count(StoryShare.share_id)).filter(StoryShare.story_id == story.story_id).scalar() or 0

        viewed_by_me = False
        liked_by_me = False
        if current_user_id:
            viewed_by_me = (
                db.query(StoryView.view_id)
                .filter(StoryView.story_id == story.story_id, StoryView.user_id == current_user_id)
                .first()
                is not None
            )
            liked_by_me = (
                db.query(StoryLike.story_likes_id)
                .filter(StoryLike.story_id == story.story_id, StoryLike.user_id == current_user_id)
                .first()
                is not None
            )

    owner_data = None
    if story.owner:
        owner_data = StoryUserResponse(
            id=story.owner.id,
            user_id=story.owner.id,
            username=story.owner.username or f"user_{story.owner.id}",
            avatar=story.owner.avatar_url,
            avatar_url=story.owner.avatar_url,
            full_name=story.owner.full_name or story.owner.username,
            role=story.owner.role or "influencer",
            verified=story.owner.role in ("influencer", "admin"),
        )

    original_owner_data = None
    orig_username = None
    if story.original_owner_id:
        orig_user = story.original_owner or db.get(User, story.original_owner_id)
        if orig_user:
            orig_username = orig_user.username
            original_owner_data = StoryUserResponse(
                id=orig_user.id,
                user_id=orig_user.id,
                username=orig_user.username or f"user_{orig_user.id}",
                avatar=orig_user.avatar_url,
                avatar_url=orig_user.avatar_url,
                full_name=orig_user.full_name or orig_user.username,
                role=orig_user.role or "influencer",
                verified=orig_user.role in ("influencer", "admin"),
            )

    mentions_data: List[StoryMentionItem] = []
    try:
        mentions_list = story.mentions if hasattr(story, "mentions") and story.mentions is not None else db.query(StoryMention).filter(StoryMention.story_id == story.story_id).all()
        for m in mentions_list:
            m_user = m.mentioned_user or db.get(User, m.mentioned_user_id)
            mentions_data.append(
                StoryMentionItem(
                    id=getattr(m, "id", None) or getattr(m, "mention_id", 0),
                    story_id=m.story_id,
                    mentioned_user_id=m.mentioned_user_id,
                    created_by_user_id=m.created_by_user_id,
                    username=m_user.username if m_user else None,
                    full_name=m_user.full_name if m_user else None,
                    avatar_url=m_user.avatar_url if m_user else None,
                    x=getattr(m, "x", None),
                    y=getattr(m, "y", None),
                )
            )
    except Exception:
        mentions_data = []

    now_naive = make_naive(utc_now())
    is_active = (not story.is_deleted) and (story.expires_at is None or story.expires_at > now_naive)

    if story.original_story_id and story.original_story_id != story.story_id:
        root = story.original_story or db.get(Story, story.original_story_id)
        if not root or root.is_deleted or (root.expires_at and root.expires_at <= now_naive):
            is_active = False

    is_reshare = bool(story.parent_story_id or (story.original_story_id and story.original_story_id != story.story_id))

    can_reshare = False
    already_reshared = False
    if current_user_id and current_user_id != story.user_id and is_active:
        is_mentioned = any(m.mentioned_user_id == current_user_id for m in mentions_data)
        if is_mentioned:
            orig_id = story.original_story_id or story.story_id
            existing_active = db.query(Story.story_id).filter(
                Story.user_id == current_user_id,
                or_(
                    Story.parent_story_id == story.story_id,
                    Story.original_story_id == orig_id,
                    Story.original_story_id == story.story_id,
                ),
                Story.is_deleted == False,
                Story.expires_at > now_naive,
            ).first()
            if existing_active is not None:
                already_reshared = True
                can_reshare = False
            else:
                already_reshared = False
                can_reshare = True

    return StoryItemResponse(
        story_id=story.story_id,
        id=story.story_id,
        user_id=story.user_id,
        author_id=story.user_id,
        media_url=story.media_url,
        imageUrl=story.media_url,
        media_type=story.media_type or "image",
        created_at=format_iso(story.created_at) or utc_now().isoformat(),
        expires_at=format_iso(story.expires_at) or (utc_now() + timedelta(hours=24)).isoformat(),
        caption=story.caption,
        content=story.caption,
        audience=story.audience or "PUBLIC",
        is_active=is_active,
        has_active_story=is_active,
        music_id=story.music_id,
        music_title=story.music_title,
        music_artist=story.music_artist,
        music_url=story.music_url,
        music_thumbnail=story.music_thumbnail,
        music_duration=story.music_duration or 60.0,
        music_start_time=story.music_start_time or 0.0,
        likes_count=likes_count,
        replies_count=replies_count,
        views_count=views_count,
        shares_count=shares_count,
        viewed_by_me=viewed_by_me,
        liked_by_me=liked_by_me,
        username=story.owner.username if story.owner else f"user_{story.user_id}",
        user=owner_data,
        parent_story_id=story.parent_story_id,
        original_story_id=story.original_story_id,
        original_owner_id=story.original_owner_id,
        original_username=orig_username,
        original_user=original_owner_data,
        is_reshare=is_reshare,
        can_reshare=can_reshare,
        already_reshared=already_reshared,
        mentions=mentions_data,
        status=story.status or ("deleted" if story.is_deleted else ("expired" if not is_active else "active")),
    )


def normalize_audience(aud: Optional[Any], is_admin: bool = False) -> str:
    if is_admin:
        return "PUBLIC"
    if not aud:
        return "PUBLIC"
    val = aud.value if hasattr(aud, "value") else str(aud)
    val = val.strip().upper()
    if val in ("CLOSE", "CLOSE_FRIEND", "CLOSE_FRIENDS"):
        return "CLOSE_FRIENDS"
    if val in ("FOLLOWER", "FOLLOWERS"):
        return "FOLLOWERS"
    return "PUBLIC"


def story_to_slide(story_item: StoryItemResponse, creator_name: str) -> StorySlideResponse:
    music_label = None
    if story_item.music_title:
        music_label = f"{story_item.music_title} – {story_item.music_artist or 'Tamil Music'} 🎵"

    return StorySlideResponse(
        id=story_item.id,
        story_id=story_item.story_id,
        imageUrl=story_item.media_url,
        media_url=story_item.media_url,
        media_type=story_item.media_type,
        caption=story_item.caption,
        content=story_item.content,
        audience=story_item.audience or "PUBLIC",
        duration=30000,
        created_at=story_item.created_at,
        expires_at=story_item.expires_at,
        liked=story_item.liked_by_me,
        likes_count=story_item.likes_count,
        views_count=story_item.views_count,
        shares_count=story_item.shares_count,
        replies_count=story_item.replies_count,
        musicTrack=music_label,
        music_url=story_item.music_url,
        replyPlaceholder=f"Reply to {creator_name}...",
        parent_story_id=story_item.parent_story_id,
        original_story_id=story_item.original_story_id,
        original_owner_id=story_item.original_owner_id,
        original_username=story_item.original_username,
        is_reshare=story_item.is_reshare,
        can_reshare=story_item.can_reshare,
        already_reshared=story_item.already_reshared,
        mentions=story_item.mentions,
        status=story_item.status,
    )
