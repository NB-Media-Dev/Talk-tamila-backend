"""@mentions on stories: user search and adding a mention."""

import logging
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.common.models.social import Notification, Follow
from app.common.models.moderation import UserBlock
from app.common.models.story import (
    Story,
    StoryMention,
)
from app.common.models.user import User
from app.common.schemas.story import (
    MentionUserSearchItem,
)

from app.common.services.story.story_helpers import (
    make_naive,
    utc_now,
)

logger = logging.getLogger(__name__)


class StoryMentionService:
    @staticmethod
    def search_mention_users(
        q: str,
        current_user: User,
        db: Session,
        limit: int = 20,
        story_id: Optional[int] = None,
    ) -> List[MentionUserSearchItem]:
        query = db.query(User).filter(User.user_id != current_user.id, User.is_active.is_(True))
        term = q.strip().lstrip("@")
        if term:
            like = f"%{term}%"
            query = query.filter(
                or_(
                    User.username.ilike(like),
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    func.concat(User.first_name, " ", User.last_name).ilike(like),
                )
            )
        users = query.order_by(User.first_name.asc(), User.user_id.asc()).limit(limit * 2).all()

        blocked_ids = {
            r[0] for r in db.query(UserBlock.blocked_id).filter(UserBlock.blocker_id == current_user.id).all()
        } | {
            r[0] for r in db.query(UserBlock.blocker_id).filter(UserBlock.blocked_id == current_user.id).all()
        }

        following_ids = {
            r[0] for r in db.query(Follow.following_id).filter(Follow.follower_id == current_user.id).all()
        }

        already_mentioned_ids = set()
        if story_id:
            already_mentioned_ids = {
                r[0]
                for r in db.query(StoryMention.mentioned_user_id)
                .filter(StoryMention.story_id == story_id)
                .all()
            }

        results = []
        for u in users:
            if u.user_id in blocked_ids:
                continue
            results.append(
                MentionUserSearchItem(
                    id=u.user_id,
                    user_id=u.user_id,
                    username=u.username or f"user_{u.user_id}",
                    full_name=u.full_name or u.username,
                    avatar_url=u.avatar_url,
                    role=u.role or "influencer",
                    is_following=u.user_id in following_ids,
                    is_blocked=False,
                    is_already_mentioned=u.user_id in already_mentioned_ids,
                )
            )
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def add_mention_to_story(
        story_id: int,
        mentioned_user_id: int,
        x: Optional[float],
        y: Optional[float],
        current_user: User,
        db: Session,
    ) -> dict:
        story = db.get(Story, story_id)
        if not story or story.is_deleted:
            raise HTTPException(status_code=404, detail="Story not found.")
        if story.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the story owner can add mentions.")

        target = db.query(User).filter(User.user_id == mentioned_user_id, User.is_active.is_(True)).first()
        if not target:
            raise HTTPException(status_code=404, detail="User to mention not found.")

       
        is_blocked = db.query(UserBlock).filter(
            or_(
                and_(UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == mentioned_user_id),
                and_(UserBlock.blocker_id == mentioned_user_id, UserBlock.blocked_id == current_user.id),
            )
        ).first() is not None
        if is_blocked:
            raise HTTPException(status_code=400, detail=f"Cannot mention @{target.username}: user is blocked.")

        existing = db.query(StoryMention).filter(
            StoryMention.story_id == story.story_id,
            StoryMention.mentioned_user_id == mentioned_user_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"@{target.username} has already been mentioned in this story slide.",
            )

        mention = StoryMention(
            story_id=story.story_id,
            mentioned_user_id=mentioned_user_id,
            created_by_user_id=current_user.id,
            owner_user_id=current_user.id,
            x=x,
            y=y,
            created_at=make_naive(utc_now()),
        )
        db.add(mention)

        if mentioned_user_id != current_user.id:
            notif = Notification(
                user_id=mentioned_user_id,
                type="STORY_MENTION",
                message=f"{current_user.username} mentioned you in their story",
                reference_id=story.story_id,
                is_read=False,
                created_at=make_naive(utc_now()),
            )
            db.add(notif)

        db.commit()
        return {"success": True, "message": f"@{target.username} has been mentioned in your story."}
