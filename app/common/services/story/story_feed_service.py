"""Read-side story lists: feeds, a user's stories, single story, saved, archived, my stories."""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.common.models.social import Follow, CloseFriend
from app.common.models.story import (
    Story,
    StoryMute,
    StorySave,
)
from app.common.models.user import User
from app.common.schemas.story import (
    StoryGroupResponse,
    StoryItemResponse,
    StoryUserResponse,
)

from app.common.services.story.story_helpers import (
    DEFAULT_DURATION_HOURS,
    build_story_item,
    fetch_batch_story_stats,
    format_iso,
    get_time_ago,
    is_story_root_active,
    make_naive,
    normalize_audience,
    story_to_slide,
    utc_now,
)

logger = logging.getLogger(__name__)


class StoryFeedService:
    @staticmethod
    def get_owner_story_feed(current_user: User, db: Session):
        from app.common.schemas.story import SlideOwnerFeedResponse, StoryOwnerFeedResponse

        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        stories = (
            db.query(Story)
            .filter(
                Story.user_id == current_user.id,
                Story.is_deleted.is_(False),
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
            .order_by(desc(Story.created_at))
            .all()
        )
        if not stories:
            return []

        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user.id, db)

        slides = [
            SlideOwnerFeedResponse(
                id=s.story_id,
                content=s.caption,
                imageUrl=s.media_url,
                media_url=s.media_url,
                views_count=batch_stats["views"].get(s.story_id, 0),
            )
            for s in stories
        ]
        return [
            StoryOwnerFeedResponse(
                story_id=stories[0].story_id,
                username=current_user.username or "Your Story",
                author_id=current_user.id,
                slides=slides,
            )
        ]

    @staticmethod
    def get_stories_feed(
        current_user: User,
        db: Session,
        limit: int = 20,
        offset: int = 0,
    ) -> List[StoryItemResponse]:
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        query = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                Story.is_deleted.is_(False),
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
        )

        caller_id = int(getattr(current_user, "user_id", None) or getattr(current_user, "id", None))
        muted_ids = [
            r[0] for r in db.query(StoryMute.muted_user_id).filter(StoryMute.user_id == caller_id).all()
        ]

        if not current_user.is_admin:
            following_ids = [
                r[0] for r in db.query(Follow.following_id).filter(Follow.follower_id == caller_id).all()
            ]
            cf_creator_ids = [
                r[0] for r in db.query(CloseFriend.user_id).filter(CloseFriend.friend_id == caller_id).all()
            ]

            audience_conditions = [
                func.upper(Story.audience).in_(["PUBLIC"])
            ]
            if following_ids:
                audience_conditions.append(
                    and_(
                        func.upper(Story.audience).in_(["FOLLOWERS", "FOLLOWER"]),
                        Story.user_id.in_(following_ids),
                    )
                )
            if cf_creator_ids:
                audience_conditions.append(
                    and_(
                        func.upper(Story.audience).in_(["CLOSE_FRIENDS", "CLOSE", "CLOSE_FRIEND"]),
                        Story.user_id.in_(cf_creator_ids),
                    )
                )

            privacy_condition = or_(
                Story.user_id == caller_id,
                and_(
                    ~Story.user_id.in_(muted_ids) if muted_ids else True,
                    or_(*audience_conditions),
                ),
            )
            query = query.filter(privacy_condition)
        elif muted_ids:
            query = query.filter(or_(Story.user_id == caller_id, ~Story.user_id.in_(muted_ids)))

        stories = (
            query.order_by(desc(Story.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        stories = [s for s in stories if is_story_root_active(s, db, now_naive)]
        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user.id, db)
        return [build_story_item(s, current_user.id, db, batch_stats=batch_stats) for s in stories]

    @staticmethod
    def list_active_stories(
        current_user: Optional[User],
        db: Session,
        role_filter: Optional[str] = None,
    ) -> List[StoryGroupResponse]:
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        query = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                Story.is_deleted.is_(False),
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
        )

        if role_filter:
            query = query.join(Story.owner).filter(User.role == role_filter)

        active_stories = query.order_by(desc(Story.created_at)).all()
        caller_id = current_user.id if current_user else None
        is_admin = current_user.is_admin if current_user else False

        muted_ids = set()
        following_ids = set()
        cf_creator_ids = set()
        if current_user:
            muted_rows = db.query(StoryMute.muted_user_id).filter(StoryMute.user_id == current_user.id).all()
            muted_ids = {r[0] for r in muted_rows}
            following_rows = db.query(Follow.following_id).filter(Follow.follower_id == current_user.id).all()
            following_ids = {r[0] for r in following_rows}
            cf_rows = db.query(CloseFriend.user_id).filter(CloseFriend.friend_id == current_user.id).all()
            cf_creator_ids = {r[0] for r in cf_rows}

        def can_view(s: Story) -> bool:
            aud = normalize_audience(s.audience)
            if not caller_id:
                return aud == "PUBLIC"
            if s.user_id == caller_id:
                return True
            if s.user_id in muted_ids:
                return False
            if is_admin:
                return True
            if aud == "PUBLIC":
                return True
            if aud == "FOLLOWERS":
                return s.user_id in following_ids
            if aud == "CLOSE_FRIENDS":
                return s.user_id in cf_creator_ids
            return False

        visible_stories = [s for s in active_stories if can_view(s) and is_story_root_active(s, db, now_naive)]

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
            creator_name = data["user"].username
            slides_list = [story_to_slide(s, creator_name) for s in stories_list]

            all_viewed = all(s.viewed_by_me for s in stories_list) if caller_id else False
            has_unseen = any(not s.viewed_by_me for s in stories_list) if caller_id else True
            is_self = bool(caller_id and uid == caller_id)
            first_story = stories_list[0] if stories_list else None

            result_groups.append(
                StoryGroupResponse(
                    id=uid,
                    user=data["user"],
                    username=creator_name,
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
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        stories = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                Story.user_id == current_user.id,
                Story.is_deleted.is_(False),
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
            .order_by(desc(Story.created_at))
            .all()
        )
        stories = [s for s in stories if is_story_root_active(s, db, now_naive)]
        story_ids = [s.story_id for s in stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user.id, db)
        return [build_story_item(s, current_user.id, db, batch_stats=batch_stats) for s in stories]

    @staticmethod
    def get_user_stories(target_user_id: int, current_user_id: Optional[int], db: Session) -> List[StoryItemResponse]:
        now_naive = make_naive(utc_now())
        cutoff = now_naive - timedelta(hours=DEFAULT_DURATION_HOURS)

        stories = (
            db.query(Story)
            .options(joinedload(Story.owner))
            .filter(
                Story.user_id == target_user_id,
                Story.is_deleted.is_(False),
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
                Story.created_at >= cutoff,
            )
            .order_by(desc(Story.created_at))
            .all()
        )
        if not stories:
            return []

        caller = db.get(User, current_user_id) if current_user_id else None
        is_admin = caller.is_admin if caller else False

        is_following = False
        is_close_friend = False
        if current_user_id and current_user_id != target_user_id:
            is_muted = (
                db.query(StoryMute)
                .filter(StoryMute.user_id == current_user_id, StoryMute.muted_user_id == target_user_id)
                .first()
                is not None
            )
            if is_muted:
                return []

            is_following = (
                db.query(Follow)
                .filter(Follow.follower_id == current_user_id, Follow.following_id == target_user_id)
                .first()
                is not None
            )
            is_close_friend = (
                db.query(CloseFriend)
                .filter(CloseFriend.user_id == target_user_id, CloseFriend.friend_id == current_user_id)
                .first()
                is not None
            )

        def can_view(s: Story) -> bool:
            if not current_user_id:
                return normalize_audience(s.audience) == "PUBLIC"
            if target_user_id == current_user_id or is_admin:
                return True
            aud = normalize_audience(s.audience)
            if aud == "PUBLIC":
                return True
            if aud == "FOLLOWERS":
                return is_following
            if aud == "CLOSE_FRIENDS":
                return is_close_friend
            return False

        visible_stories = [s for s in stories if can_view(s) and is_story_root_active(s, db, now_naive)]
        story_ids = [s.story_id for s in visible_stories]
        batch_stats = fetch_batch_story_stats(story_ids, current_user_id, db)
        return [build_story_item(s, current_user_id, db, batch_stats=batch_stats) for s in visible_stories]

    @staticmethod
    def get_single_story(story_id: int, current_user_id: Optional[int], db: Session) -> StoryItemResponse:
        story = db.get(Story, story_id)
        if not story or story.is_deleted:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.expires_at and story.expires_at < make_naive(utc_now()):
            raise HTTPException(status_code=404, detail="Story not found")

        caller = db.get(User, current_user_id) if current_user_id else None
        is_admin = caller.is_admin if caller else False
        aud = normalize_audience(story.audience)

        if caller and (story.user_id == caller.id or is_admin):
            pass
        elif aud == "PUBLIC":
            pass
        elif not caller:
            raise HTTPException(status_code=403, detail="Story is private.")
        elif aud == "FOLLOWERS":
            is_following = db.query(Follow).filter(
                Follow.follower_id == caller.id,
                Follow.following_id == story.user_id,
            ).first() is not None
            if not is_following:
                raise HTTPException(status_code=403, detail="Story only available to followers.")
        elif aud == "CLOSE_FRIENDS":
            is_close_friend = db.query(CloseFriend).filter(
                CloseFriend.user_id == story.user_id,
                CloseFriend.friend_id == caller.id,
            ).first() is not None
            if not is_close_friend:
                raise HTTPException(status_code=403, detail="Story only available to close friends.")

        if story.original_story_id and story.original_story_id != story.story_id:
            root = story.original_story or db.get(Story, story.original_story_id)
            if not root or root.is_deleted or (root.expires_at and root.expires_at <= make_naive(utc_now())):
                raise HTTPException(status_code=404, detail="Story not found or original story expired/deleted.")

        return build_story_item(story, current_user_id, db)

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
    def get_archived_stories(current_user: User, db: Session):
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
    def get_my_stories_with_metrics(current_user: User, db: Session) -> list:
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
