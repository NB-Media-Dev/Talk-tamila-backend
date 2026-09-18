import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.common.models.social import Notification
from app.common.models.story import (
    Story,
    StoryLike,
    StoryMute,
    StoryReply,
    StoryReport,
    StorySave,
    StoryShare,
    StoryView,
)
from app.common.models.user import User
from app.common.services.music_service import MusicService
from app.common.schemas.story import (
    ActivityLiker,
    ActivityViewer,
    StoryActivityResponse,
    StoryBatchResponse,
    StoryGroupResponse,
    StoryItemResponse,
    StoryReplyResponse,
    StoryShareResponse,
    StorySlideResponse,
    StoryUserResponse,
)

logger = logging.getLogger("talktamila.story_service")

DEFAULT_DURATION_HOURS = 24
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


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


async def file_to_base64_data_url(file: UploadFile) -> Tuple[str, str]:
    """Encodes uploaded story media to a Base64 Data URL.
    Stored strictly in MySQL demousertable (LONGTEXT) — NEVER saved to the filesystem uploads/.
    """
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = file.content_type

    if not content_type or content_type == "application/octet-stream":
        if ext in VIDEO_EXTENSIONS:
            content_type = "video/mp4"
        elif ext == ".png":
            content_type = "image/png"
        elif ext == ".gif":
            content_type = "image/gif"
        elif ext == ".webp":
            content_type = "image/webp"
        else:
            content_type = "image/jpeg"

    media_type = "video" if ("video" in content_type or ext in VIDEO_EXTENSIONS) else "image"
    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"
    return data_url, media_type


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

    views_rows = db.query(StoryView.story_id, func.count(StoryView.view_id)).filter(StoryView.story_id.in_(story_ids)).group_by(StoryView.story_id).all()
    likes_rows = db.query(StoryLike.story_id, func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id.in_(story_ids)).group_by(StoryLike.story_id).all()
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
        views_count = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id == story.story_id).scalar() or 0
        likes_count = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id == story.story_id).scalar() or 0
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
            userName=story.owner.username or f"user_{story.owner.id}",
            username=story.owner.username or f"user_{story.owner.id}",
            avatar=story.owner.avatar_url,
            avatar_url=story.owner.avatar_url,
            full_name=story.owner.full_name or story.owner.username,
            role=story.owner.role or "influencer",
            verified=story.owner.role in ("influencer", "admin"),
        )

    now_naive = make_naive(utc_now())
    is_active = (story.expires_at is None) or (story.expires_at > now_naive)

    return StoryItemResponse(
        story_id=story.story_id,
        id=story.story_id,
        user_id=story.user_id,
        media_url=story.media_url,
        imageUrl=story.media_url,
        media_type=story.media_type or "image",
        created_at=format_iso(story.created_at) or utc_now().isoformat(),
        expires_at=format_iso(story.expires_at) or (utc_now() + timedelta(hours=24)).isoformat(),
        caption=story.caption,
        audience=story.audience or "public",
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
        user=owner_data,
    )


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
        duration=5000,
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
    )


class StoryService:
    @staticmethod
    def list_active_groups(
        current_user: Optional[User],
        db: Session,
        role_filter: Optional[str] = None,
    ) -> List[StoryGroupResponse]:
        """Fetch active 24-hour stories grouped by user matching Instagram concept:
        - Self stories are placed first with is_my_story = True
        - All other creators follow
        - Provides both slides for Previewstories.tsx and stories for full metadata
        - Unseen stories indicator (gradient ring) vs all-viewed indicator (grey ring)
        """
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        query = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
        )

        if role_filter:
            query = query.join(Story.owner).filter(User.role == role_filter)

        active_stories = query.order_by(desc(Story.created_at)).all()
        caller_id = current_user.id if current_user else None

        muted_ids = set()
        if current_user:
            muted_rows = db.query(StoryMute.muted_user_id).filter(StoryMute.user_id == current_user.id).all()
            muted_ids = {r[0] for r in muted_rows}

        visible_stories = [
            s for s in active_stories
            if not (caller_id and s.user_id in muted_ids and s.user_id != caller_id)
        ]

        story_ids = [s.story_id for s in visible_stories]
        batch_stats = fetch_batch_story_stats(story_ids, caller_id, db)

        groups_dict: Dict[int, Dict[str, Any]] = {}
        for story in visible_stories:
            uid = story.user_id
            if uid not in groups_dict:
                user_obj = story.owner
                uname = user_obj.username if user_obj else f"user_{uid}"
                avatar = user_obj.avatar_url if user_obj else None
                user_role = user_obj.role if user_obj else "influencer"
                fname = user_obj.full_name if user_obj else uname

                user_res = StoryUserResponse(
                    id=uid,
                    user_id=uid,
                    userName=uname,
                    username=uname,
                    avatar=avatar,
                    avatar_url=avatar,
                    full_name=fname,
                    role=user_role,
                    verified=user_role in ("influencer", "admin"),
                )
                groups_dict[uid] = {
                    "user": user_res,
                    "stories": [],
                    "latest_dt": story.created_at or now_naive,
                    "music_track": None,
                }

            story_item = build_story_item(story, caller_id, db, batch_stats=batch_stats)
            groups_dict[uid]["stories"].append(story_item)
            if story.music_title and not groups_dict[uid]["music_track"]:
                groups_dict[uid]["music_track"] = f"{story.music_title} – {story.music_artist or 'Tamil Music'} 🎵"

            if story.created_at and story.created_at > groups_dict[uid]["latest_dt"]:
                groups_dict[uid]["latest_dt"] = story.created_at

        result_groups: List[StoryGroupResponse] = []
        for uid, data in groups_dict.items():
            stories_list: List[StoryItemResponse] = data["stories"]
            creator_name = data["user"].userName
            slides_list = [story_to_slide(s, creator_name) for s in stories_list]

            all_viewed = all(s.viewed_by_me for s in stories_list) if caller_id else False
            has_unseen = any(not s.viewed_by_me for s in stories_list) if caller_id else True
            is_self = bool(caller_id and uid == caller_id)
            first_story = stories_list[0] if stories_list else None

            result_groups.append(
                StoryGroupResponse(
                    id=uid,
                    user=data["user"],
                    userName=data["user"].userName,
                    avatar=data["user"].avatar,
                    verified=data["user"].verified,
                    role=data["user"].role,
                    timeAgo=get_time_ago(data["latest_dt"]),
                    musicTrack=data["music_track"],
                    slides=slides_list,
                    stories=stories_list,
                    stories_count=len(stories_list),
                    latest_story_created_at=format_iso(data["latest_dt"]) or utc_now().isoformat(),
                    is_my_story=is_self,
                    all_viewed=all_viewed,
                    has_unseen_stories=has_unseen,
                    has_active_story=True,
                    media_url=first_story.media_url if first_story else None,
                    story_id=first_story.story_id if first_story else None,
                )
            )

        if caller_id:
            result_groups.sort(key=lambda g: (0 if g.is_my_story else 1, 1 if g.all_viewed else 0))

        return result_groups

    @staticmethod
    def get_my_stories(current_user: User, db: Session) -> List[StoryItemResponse]:
        """Fetch active stories strictly belonging to current authenticated user ('Your Story')."""
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        stories = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                Story.user_id == current_user.id,
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
            .order_by(desc(Story.created_at))
            .all()
        )
        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user.id, db)
        return [build_story_item(s, current_user.id, db, batch_stats=batch_stats) for s in stories]

    @staticmethod
    def get_user_stories(target_user_id: int, current_user_id: Optional[int], db: Session) -> List[StoryItemResponse]:
        """Fetch active stories for any other specific creator/user."""
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        stories = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                Story.user_id == target_user_id,
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
            .order_by(desc(Story.created_at))
            .all()
        )
        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user_id, db)
        return [build_story_item(s, current_user_id, db, batch_stats=batch_stats) for s in stories]

    @staticmethod
    def get_story_by_id(story_id: int, current_user_id: Optional[int], db: Session) -> StoryItemResponse:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        return build_story_item(story, current_user_id, db)

    @staticmethod
    async def upload_single(
        file: UploadFile,
        caption: Optional[str],
        audience: Optional[str],
        music_data: Optional[str],
        current_user: User,
        db: Session,
        music_start_time: Optional[float] = 0.0,
    ) -> StoryItemResponse:
        """Upload single photo/video story directly to MySQL LONGTEXT as Base64 Data URL."""
        data_url, media_type = await file_to_base64_data_url(file)

        music_info: Dict[str, Any] = {}
        if music_data:
            try:
                music_info = json.loads(music_data)
            except Exception:
                pass

        now_naive = make_naive(utc_now())
        expires_naive = now_naive + timedelta(hours=DEFAULT_DURATION_HOURS)

        music_dur = None
        resolved_music_id = None
        if music_info:
            music_dur = max(1.0, min(float(music_info.get("music_duration", 60.0)), 60.0))
            resolved_music_id = MusicService.resolve_or_create_music_track(
                db=db,
                music_id=music_info.get("music_id"),
                music_title=music_info.get("music_title") or music_info.get("title"),
                music_artist=music_info.get("music_artist") or music_info.get("artist"),
                music_url=music_info.get("music_url") or music_info.get("audio_url"),
                music_thumbnail=music_info.get("music_thumbnail") or music_info.get("cover_url"),
                music_duration=music_dur,
            )

        story = Story(
            user_id=current_user.id,
            media_url=data_url,
            media_type=media_type,
            caption=caption,
            audience=audience or "public",
            created_at=now_naive,
            expires_at=expires_naive,
            music_id=resolved_music_id,
            music_title=music_info.get("music_title") or music_info.get("title"),
            music_artist=music_info.get("music_artist") or music_info.get("artist"),
            music_url=music_info.get("music_url") or music_info.get("audio_url"),
            music_thumbnail=music_info.get("music_thumbnail") or music_info.get("cover_url"),
            music_duration=music_dur,
            music_start_time=max(0.0, float(music_start_time or 0.0)),
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        logger.info("Story %s uploaded by user %s to MySQL demousertable", story.story_id, current_user.id)
        return build_story_item(story, current_user.id, db)

    @staticmethod
    async def upload_multiple(
        files: List[UploadFile],
        captions: Optional[str],
        audience: Optional[str],
        music_data: Optional[str],
        current_user: User,
        db: Session,
        music_start_time: Optional[float] = 0.0,
    ) -> StoryBatchResponse:
        """Batch upload multiple slides directly to MySQL demousertable."""
        if not files:
            raise HTTPException(status_code=400, detail="No files provided.")

        parsed_captions: List[str] = []
        if captions:
            try:
                parsed = json.loads(captions)
                if isinstance(parsed, list):
                    parsed_captions = [str(c) for c in parsed]
                elif isinstance(parsed, str):
                    parsed_captions = [parsed]
            except Exception:
                parsed_captions = [captions]

        music_info: Dict[str, Any] = {}
        if music_data:
            try:
                music_info = json.loads(music_data)
            except Exception:
                pass

        music_dur = None
        resolved_music_id = None
        if music_info:
            music_dur = max(1.0, min(float(music_info.get("music_duration", 60.0)), 60.0))
            resolved_music_id = MusicService.resolve_or_create_music_track(
                db=db,
                music_id=music_info.get("music_id"),
                music_title=music_info.get("music_title") or music_info.get("title"),
                music_artist=music_info.get("music_artist") or music_info.get("artist"),
                music_url=music_info.get("music_url") or music_info.get("audio_url"),
                music_thumbnail=music_info.get("music_thumbnail") or music_info.get("cover_url"),
                music_duration=music_dur,
            )

        now_naive = make_naive(utc_now())
        expires_naive = now_naive + timedelta(hours=DEFAULT_DURATION_HOURS)

        created_stories: List[Story] = []
        for idx, f in enumerate(files):
            data_url, media_type = await file_to_base64_data_url(f)
            item_caption = parsed_captions[idx] if idx < len(parsed_captions) else (parsed_captions[0] if parsed_captions else None)

            story = Story(
                user_id=current_user.id,
                media_url=data_url,
                media_type=media_type,
                caption=item_caption,
                audience=audience or "public",
                created_at=now_naive + timedelta(milliseconds=idx * 10),
                expires_at=expires_naive,
                music_id=resolved_music_id,
                music_title=music_info.get("music_title") or music_info.get("title"),
                music_artist=music_info.get("music_artist") or music_info.get("artist"),
                music_url=music_info.get("music_url") or music_info.get("audio_url"),
                music_thumbnail=music_info.get("music_thumbnail") or music_info.get("cover_url"),
                music_duration=music_dur,
                music_start_time=max(0.0, float(music_start_time or 0.0)),
            )
            db.add(story)
            created_stories.append(story)

        db.commit()
        for s in created_stories:
            db.refresh(s)

        items = [build_story_item(s, current_user.id, db) for s in created_stories]
        return StoryBatchResponse(
            success=True,
            message=f"Successfully published {len(created_stories)} stories to MySQL.",
            total_published=len(created_stories),
            stories=items,
        )

    @staticmethod
    def record_view(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = (
            db.query(StoryView)
            .filter(StoryView.story_id == story_id, StoryView.user_id == current_user.id)
            .first()
        )
        if not existing:
            view = StoryView(
                story_id=story_id,
                user_id=current_user.id,
                viewed_at=make_naive(utc_now()),
            )
            db.add(view)
            db.commit()

        views_count = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id == story_id).scalar() or 0
        return {"success": True, "message": "Story viewed", "story_id": story_id, "views_count": views_count}

    @staticmethod
    def like_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if story.user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot like your own story. Liking is only available for others' stories.",
            )

        existing = (
            db.query(StoryLike)
            .filter(StoryLike.story_id == story_id, StoryLike.user_id == current_user.id)
            .first()
        )
        if not existing:
            like = StoryLike(
                story_id=story_id,
                user_id=current_user.id,
                user_name=current_user.username,
            )
            db.add(like)
            if story.user_id != current_user.id:
                try:
                    notif = Notification(
                        user_id=story.user_id,
                        type="story_like",
                        message=f"{current_user.username} liked your story",
                        reference_id=story_id,
                        is_read=False,
                        created_at=make_naive(utc_now()),
                    )
                    db.add(notif)
                except Exception:
                    pass
            db.commit()

        likes_count = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id == story_id).scalar() or 0
        return {"story_id": story_id, "likes_count": likes_count, "liked_by_me": True, "success": True}

    @staticmethod
    def unlike_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = (
            db.query(StoryLike)
            .filter(StoryLike.story_id == story_id, StoryLike.user_id == current_user.id)
            .first()
        )
        if existing:
            db.delete(existing)
            db.commit()

        likes_count = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id == story_id).scalar() or 0
        return {"story_id": story_id, "likes_count": likes_count, "liked_by_me": False, "success": True}

    @staticmethod
    def record_pause_state(
        story_id: int,
        action: str,
        progress_ms: Optional[int],
        slide_index: Optional[int],
        current_user: User,
        db: Session,
    ) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        logger.info(
            "User %s %s story %s (slide: %s, progress: %sms)",
            current_user.id,
            action,
            story_id,
            slide_index,
            progress_ms,
        )
        return {
            "success": True,
            "action": action,
            "story_id": story_id,
            "slide_index": slide_index,
            "progress_ms": progress_ms,
            "user_id": current_user.id,
        }

    @staticmethod
    def comment_story(story_id: int, text: str, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if story.user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reply to your own story. Replying is only available for others' stories.",
            )

        reply = StoryReply(
            story_id=story_id,
            user_id=current_user.id,
            text=text,
            created_at=make_naive(utc_now()),
        )
        db.add(reply)

        if story.user_id != current_user.id:
            try:
                notif = Notification(
                    user_id=story.user_id,
                    type="story_reply",
                    message=f"{current_user.username} replied to your story: {text[:50]}",
                    reference_id=story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
                db.add(notif)
            except Exception:
                pass

        db.commit()
        db.refresh(reply)
        return {
            "success": True,
            "message": "Reply sent successfully",
            "reply_id": reply.reply_id,
            "text": reply.text,
            "created_at": format_iso(reply.created_at) or utc_now().isoformat(),
        }

    @staticmethod
    def get_comments(story_id: int, db: Session) -> List[StoryReplyResponse]:
        replies = (
            db.query(StoryReply)
            .options(joinedload(StoryReply.user))
            .filter(StoryReply.story_id == story_id)
            .order_by(desc(StoryReply.created_at))
            .all()
        )
        return [
            StoryReplyResponse(
                reply_id=r.reply_id,
                story_id=r.story_id,
                user_id=r.user_id,
                text=r.text,
                created_at=format_iso(r.created_at) or utc_now().isoformat(),
                username=r.user.username if r.user else f"user_{r.user_id}",
                avatar_url=r.user.avatar_url if r.user else None,
            )
            for r in replies
        ]

    @staticmethod
    def share_story(
        story_id: int,
        platform: str,
        current_user: User,
        db: Session,
        target_user_id: Optional[int] = None,
    ) -> StoryShareResponse:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        share = StoryShare(
            story_id=story_id,
            user_id=current_user.id,
            platform=platform or "copy_link",
            created_at=make_naive(utc_now()),
        )
        db.add(share)

        if target_user_id and target_user_id != current_user.id:
            try:
                notif = Notification(
                    user_id=target_user_id,
                    type="story_share",
                    message=f"{current_user.username} shared a story with you",
                    reference_id=story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
                db.add(notif)
            except Exception:
                pass

        db.commit()
        total_shares = db.query(func.count(StoryShare.share_id)).filter(StoryShare.story_id == story_id).scalar() or 0
        share_url = f"/stories/{story_id}"

        return StoryShareResponse(
            success=True,
            message="Story shared successfully",
            story_id=story_id,
            shares_count=total_shares,
            share_url=share_url,
        )

    @staticmethod
    def report_story(story_id: int, reason: str, current_user: User, db: Session, details: Optional[str] = None) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        combined_reason = f"{reason} - {details}" if details else reason
        report = StoryReport(
            story_id=story_id,
            user_id=current_user.id,
            reason=combined_reason[:255],
            created_at=make_naive(utc_now()),
        )
        db.add(report)
        db.commit()
        return {"success": True, "message": "Thank you. Your report has been submitted.", "story_id": story_id}

    @staticmethod
    def mute_creator(muted_user_id: int, current_user: User, db: Session) -> dict:
        if muted_user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot mute yourself.")

        existing = db.query(StoryMute).filter(
            StoryMute.user_id == current_user.id,
            StoryMute.muted_user_id == muted_user_id,
        ).first()
        if not existing:
            mute = StoryMute(
                user_id=current_user.id,
                muted_user_id=muted_user_id,
                created_at=make_naive(utc_now()),
            )
            db.add(mute)
            db.commit()
        return {
            "success": True,
            "message": "Stories from this user muted.",
            "muted_user_id": muted_user_id,
            "is_muted": True,
        }

    @staticmethod
    def unmute_creator(muted_user_id: int, current_user: User, db: Session) -> dict:
        existing = db.query(StoryMute).filter(
            StoryMute.user_id == current_user.id,
            StoryMute.muted_user_id == muted_user_id,
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
        return {
            "success": True,
            "message": "Stories from this user unmuted.",
            "muted_user_id": muted_user_id,
            "is_muted": False,
        }

    @staticmethod
    def get_muted_creators(current_user: User, db: Session) -> List[int]:
        rows = db.query(StoryMute.muted_user_id).filter(StoryMute.user_id == current_user.id).all()
        return [r[0] for r in rows]

    @staticmethod
    def save_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = db.query(StorySave).filter(
            StorySave.story_id == story_id,
            StorySave.user_id == current_user.id,
        ).first()

        if not existing:
            save_entry = StorySave(
                story_id=story_id,
                user_id=current_user.id,
                saved_at=make_naive(utc_now()),
            )
            db.add(save_entry)
            db.commit()

        return {
            "success": True,
            "message": "Story saved successfully",
            "story_id": story_id,
            "is_saved": True,
        }

    @staticmethod
    def unsave_story(story_id: int, current_user: User, db: Session) -> dict:
        existing = db.query(StorySave).filter(
            StorySave.story_id == story_id,
            StorySave.user_id == current_user.id,
        ).first()

        if existing:
            db.delete(existing)
            db.commit()

        return {
            "success": True,
            "message": "Story removed from saved",
            "story_id": story_id,
            "is_saved": False,
        }

    @staticmethod
    def get_saved_stories(current_user: User, db: Session) -> list:
        saves = (
            db.query(StorySave)
            .options(joinedload(StorySave.story))
            .filter(StorySave.user_id == current_user.id)
            .order_by(desc(StorySave.saved_at))
            .all()
        )
        return [
            {
                "save_id": s.save_id,
                "story_id": s.story_id,
                "saved_at": format_iso(s.saved_at),
                "media_url": s.story.media_url if s.story else None,
                "caption": s.story.caption if s.story else None,
            }
            for s in saves
            if s.story is not None
        ]

    @staticmethod
    def delete_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if current_user.id != story.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author who created this story can delete it.",
            )

        try:
            db.query(StorySave).filter(StorySave.story_id == story_id).delete(synchronize_session=False)
            db.query(StoryReport).filter(StoryReport.story_id == story_id).delete(synchronize_session=False)
            db.query(StoryShare).filter(StoryShare.story_id == story_id).delete(synchronize_session=False)
            db.query(StoryReply).filter(StoryReply.story_id == story_id).delete(synchronize_session=False)
            db.query(StoryLike).filter(StoryLike.story_id == story_id).delete(synchronize_session=False)
            db.query(StoryView).filter(StoryView.story_id == story_id).delete(synchronize_session=False)
        except Exception as e:
            logger.warning("Cascading cleanup note for story %s: %s", story_id, e)

        db.delete(story)
        db.commit()
        logger.info("Story %s deleted by user %s", story_id, current_user.id)
        return {"success": True, "message": "Story deleted successfully", "story_id": story_id}

    @staticmethod
    def get_activity(story_id: int, current_user: User, db: Session) -> StoryActivityResponse:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if story.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only the story author can view viewer activity.")

        likes = db.query(StoryLike).options(joinedload(StoryLike.user)).filter(StoryLike.story_id == story_id).all()
        likers_list: List[ActivityLiker] = []
        liked_by_me = False
        for l in likes:
            if l.user_id == current_user.id:
                liked_by_me = True
            u = l.user
            likers_list.append(
                ActivityLiker(
                    user_id=l.user_id,
                    username=u.username if u else (l.user_name or f"user_{l.user_id}"),
                    avatar_url=u.avatar_url if u else None,
                    full_name=u.full_name if u else (l.user_name or f"User {l.user_id}"),
                )
            )

        views = (
            db.query(StoryView)
            .options(joinedload(StoryView.user))
            .filter(StoryView.story_id == story_id)
            .order_by(desc(StoryView.viewed_at))
            .all()
        )
        viewers_list: List[ActivityViewer] = []
        for v in views:
            u = v.user
            viewers_list.append(
                ActivityViewer(
                    user_id=v.user_id,
                    username=u.username if u else f"user_{v.user_id}",
                    avatar_url=u.avatar_url if u else None,
                    full_name=u.full_name if u else f"User {v.user_id}",
                    viewed_at=format_iso(v.viewed_at) or utc_now().isoformat(),
                )
            )

        return StoryActivityResponse(
            story_id=story_id,
            total_views=len(viewers_list),
            total_likes=len(likers_list),
            liked_by_me=liked_by_me,
            viewers=viewers_list,
            likers=likers_list,
        )

    @staticmethod
    def get_viewers(
        story_id: int,
        current_user: User,
        db: Session,
        page: int = 1,
        page_size: int = 20,
    ):
        """Paginated list of users who viewed a story (owner only)."""
        from app.common.schemas.story import PaginatedViewerResponse, StoryViewerItem

        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only the story owner can see viewers.")

        total = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id == story_id).scalar() or 0
        offset = (page - 1) * page_size
        rows = (
            db.query(StoryView)
            .options(joinedload(StoryView.user))
            .filter(StoryView.story_id == story_id)
            .order_by(desc(StoryView.viewed_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )
        items = [
            StoryViewerItem(
                user_id=v.user_id,
                username=v.user.username if v.user else f"user_{v.user_id}",
                full_name=v.user.full_name if v.user else None,
                avatar_url=v.user.avatar_url if v.user else None,
                viewed_at=format_iso(v.viewed_at) or utc_now().isoformat(),
            )
            for v in rows
        ]
        return PaginatedViewerResponse(
            story_id=story_id,
            total_views=total,
            page=page,
            page_size=page_size,
            viewers=items,
        )

    @staticmethod
    def get_likers(
        story_id: int,
        current_user: User,
        db: Session,
        page: int = 1,
        page_size: int = 20,
    ):
        """Paginated list of users who liked a story (owner only)."""
        from app.common.schemas.story import PaginatedLikerResponse, StoryLikerItem

        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only the story owner can see likers.")

        total = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id == story_id).scalar() or 0
        offset = (page - 1) * page_size
        rows = (
            db.query(StoryLike)
            .options(joinedload(StoryLike.user))
            .filter(StoryLike.story_id == story_id)
            .order_by(desc(StoryLike.liked_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )
        items = [
            StoryLikerItem(
                user_id=lk.user_id,
                username=lk.user.username if lk.user else (lk.user_name or f"user_{lk.user_id}"),
                full_name=lk.user.full_name if lk.user else None,
                avatar_url=lk.user.avatar_url if lk.user else None,
                liked_at=format_iso(lk.liked_at) or utc_now().isoformat(),
            )
            for lk in rows
        ]
        return PaginatedLikerResponse(
            story_id=story_id,
            total_likes=total,
            page=page,
            page_size=page_size,
            likers=items,
        )

    @staticmethod
    def get_my_stats(current_user: User, db: Session):
        """Aggregate engagement totals across all stories created by the current user."""
        from app.common.schemas.story import StoryStatsResponse

        now_naive = make_naive(utc_now())

        story_ids_rows = db.query(Story.story_id).filter(Story.user_id == current_user.id).all()
        story_ids = [r[0] for r in story_ids_rows]
        total_stories = len(story_ids)

        if not story_ids:
            return StoryStatsResponse(
                user_id=current_user.id,
                total_stories=0,
                total_views=0,
                total_likes=0,
                total_replies=0,
                total_shares=0,
                active_stories=0,
                expired_stories=0,
            )

        total_views = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id.in_(story_ids)).scalar() or 0
        total_likes = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id.in_(story_ids)).scalar() or 0
        total_replies = db.query(func.count(StoryReply.reply_id)).filter(StoryReply.story_id.in_(story_ids)).scalar() or 0
        total_shares = db.query(func.count(StoryShare.share_id)).filter(StoryShare.story_id.in_(story_ids)).scalar() or 0

        active_stories = db.query(func.count(Story.story_id)).filter(
            Story.user_id == current_user.id,
            or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
        ).scalar() or 0
        expired_stories = total_stories - active_stories

        return StoryStatsResponse(
            user_id=current_user.id,
            total_stories=total_stories,
            total_views=total_views,
            total_likes=total_likes,
            total_replies=total_replies,
            total_shares=total_shares,
            active_stories=active_stories,
            expired_stories=expired_stories,
        )

    @staticmethod
    def update_story(story_id: int, caption: Optional[str], audience: Optional[str], current_user: User, db: Session) -> Story:
        """Edit caption and/or audience of an existing story (owner only)."""
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the story owner can edit it.")

        if caption is not None:
            story.caption = caption
        if audience is not None:
            story.audience = audience

        db.commit()
        db.refresh(story)
        return build_story_item(story, current_user.id, db)

    @staticmethod
    def get_archived_stories(current_user: User, db: Session):
        """Return expired (past 30-day) stories for the authenticated user."""
        from app.common.schemas.story import StoryArchivedItem

        now_naive = make_naive(utc_now())
        cutoff_30d = now_naive - timedelta(days=30)

        stories = (
            db.query(Story)
            .filter(
                Story.user_id == current_user.id,
                Story.expires_at.isnot(None),
                Story.expires_at <= now_naive,
                Story.created_at >= cutoff_30d,
            )
            .order_by(desc(Story.created_at))
            .all()
        )

        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user.id, db)

        result = [
            StoryArchivedItem(
                story_id=s.story_id,
                id=s.story_id,
                media_url=s.media_url,
                media_type=s.media_type or "image",
                caption=s.caption,
                created_at=format_iso(s.created_at) or utc_now().isoformat(),
                expired_at=format_iso(s.expires_at) or utc_now().isoformat(),
                views_count=batch_stats["views"].get(s.story_id, 0),
                likes_count=batch_stats["likes"].get(s.story_id, 0),
            )
            for s in stories
        ]
        return result

    @staticmethod
    def react_to_story(story_id: int, emoji: str, current_user: User, db: Session) -> dict:
        """Record an emoji reaction to a story (stored as a specialised like with emoji metadata).
        Uses the StoryLike table – emoji is prepended to user_name for lightweight storage.
        """
        from app.common.schemas.story import StoryReactResponse

        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        tag = f"react:{emoji}"
        existing = (
            db.query(StoryLike)
            .filter(
                StoryLike.story_id == story_id,
                StoryLike.user_id == current_user.id,
                StoryLike.user_name == tag,
            )
            .first()
        )
        if not existing:
            like = StoryLike(
                story_id=story_id,
                user_id=current_user.id,
                user_name=tag,
                liked_at=make_naive(utc_now()),
            )
            db.add(like)
            if story.user_id != current_user.id:
                try:
                    notif = Notification(
                        user_id=story.user_id,
                        type="story_react",
                        message=f"{current_user.username} reacted {emoji} to your story",
                        reference_id=story_id,
                        is_read=False,
                        created_at=make_naive(utc_now()),
                    )
                    db.add(notif)
                except Exception:
                    pass
            db.commit()

        return StoryReactResponse(
            success=True,
            story_id=story_id,
            emoji=emoji,
            message=f"Reacted with {emoji}",
        )

    @staticmethod
    def get_my_stories_with_metrics(current_user: User, db: Session) -> list:
        """Return all stories (active + expired last 7 days) with engagement metrics for role dashboards."""
        from app.common.schemas.story import StoryWithMetrics

        now_naive = make_naive(utc_now())
        cutoff_7d = now_naive - timedelta(days=7)

        stories = (
            db.query(Story)
            .filter(
                Story.user_id == current_user.id,
                Story.created_at >= cutoff_7d,
            )
            .order_by(desc(Story.created_at))
            .all()
        )

        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user.id, db)

        result = []
        for s in stories:
            views_count = batch_stats["views"].get(s.story_id, 0)
            likes_count = batch_stats["likes"].get(s.story_id, 0)
            replies_count = batch_stats["replies"].get(s.story_id, 0)
            shares_count = batch_stats["shares"].get(s.story_id, 0)
            engagement_rate = round((likes_count + replies_count + shares_count) / views_count * 100, 2) if views_count > 0 else 0.0
            is_active = (s.expires_at is None) or (s.expires_at > now_naive)
            result.append(
                StoryWithMetrics(
                    story_id=s.story_id,
                    id=s.story_id,
                    media_url=s.media_url,
                    media_type=s.media_type or "image",
                    caption=s.caption,
                    audience=s.audience or "public",
                    created_at=format_iso(s.created_at) or utc_now().isoformat(),
                    expires_at=format_iso(s.expires_at) or utc_now().isoformat(),
                    is_active=is_active,
                    views_count=views_count,
                    likes_count=likes_count,
                    replies_count=replies_count,
                    shares_count=shares_count,
                    engagement_rate=engagement_rate,
                )
            )
        return result
