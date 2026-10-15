"""Create, upload, edit, delete and re-share stories."""

import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.common.models.social import Notification
from app.common.models.moderation import UserBlock
from app.common.models.story import (
    Story,
    StoryMention,
)
from app.common.models.user import User
from app.common.services.music_service import MusicService
from app.common.schemas.story import (
    StoryBatchResponse,
    StoryItemResponse,
    StoryReshareRequest,
)

from app.common.services.story.story_helpers import (
    DEFAULT_DURATION_HOURS,
    build_story_item,
    make_naive,
    normalize_audience,
    process_and_create_mentions,
    utc_now,
)
from app.utils.media_upload import file_to_base64_data_url

logger = logging.getLogger(__name__)


class StoryCreationService:
    @staticmethod
    def create_story(payload, current_user: User, db: Session) -> StoryItemResponse:
        media_url = getattr(payload, "media_url", None)
        caption = getattr(payload, "caption", None) or getattr(payload, "content", None)
        
        if not media_url:
            if caption:
                media_url = "gradient:insta"
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either media_url or caption/content is required to create a story.",
                )

        media_type = (getattr(payload, "media_type", "image") or "image").strip().lower()
        if media_type not in ("image", "video", "text"):
            media_type = "image"

        duration_hours = getattr(payload, "duration_hours", DEFAULT_DURATION_HOURS) or DEFAULT_DURATION_HOURS
        now_naive = make_naive(utc_now())
        expires_naive = now_naive + timedelta(hours=duration_hours)

        music_id = getattr(payload, "music_id", None)
        music_title = getattr(payload, "music_title", None)
        music_artist = getattr(payload, "music_artist", None)
        music_url = getattr(payload, "music_url", None)
        music_thumbnail = getattr(payload, "music_thumbnail", None)
        music_duration = getattr(payload, "music_duration", 60.0) or 60.0
        music_start_time = getattr(payload, "music_start_time", 0.0) or 0.0

        resolved_music_id = None
        if music_id or music_title or music_url:
            resolved_music_id = MusicService.resolve_or_create_music_track(
                db=db,
                music_id=music_id,
                music_title=music_title,
                music_artist=music_artist,
                music_url=music_url,
                music_thumbnail=music_thumbnail,
                music_duration=music_duration,
            )

        story = Story(
            user_id=current_user.id,
            username=current_user.username,
            media_url=media_url,
            media_type=media_type,
            caption=caption,
            audience=normalize_audience(getattr(payload, "audience", "PUBLIC"), is_admin=current_user.is_admin),
            created_at=now_naive,
            expires_at=expires_naive,
            music_id=resolved_music_id,
            music_title=music_title,
            music_artist=music_artist,
            music_url=music_url,
            music_thumbnail=music_thumbnail,
            music_duration=music_duration,
            music_start_time=max(0.0, float(music_start_time)),
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        process_and_create_mentions(db, story, getattr(payload, "mentions", None), caption, current_user)
        logger.info("Story %s created via JSON by user %s", story.story_id, current_user.id)
        return build_story_item(story, current_user.id, db)

    @staticmethod
    def create_text_story(payload, current_user: User, db: Session) -> StoryItemResponse:
        now_naive = make_naive(utc_now())
        duration_hours = getattr(payload, "duration_hours", DEFAULT_DURATION_HOURS) or DEFAULT_DURATION_HOURS
        expires_naive = now_naive + timedelta(hours=duration_hours)

        resolved_music_id = MusicService.resolve_or_create_music_track(
            db=db,
            music_id=getattr(payload, "music_id", None),
            music_title=getattr(payload, "music_title", None),
            music_artist=getattr(payload, "music_artist", None),
            music_url=getattr(payload, "music_url", None),
            music_thumbnail=getattr(payload, "music_thumbnail", None),
            music_duration=getattr(payload, "music_duration", 60.0) or 60.0,
        )

        theme_val = (getattr(payload, "theme", "insta") or "insta").strip().lower()
        media_url = getattr(payload, "media_url", None) or f"gradient:{theme_val}"
        caption_val = getattr(payload, "caption", None) or getattr(payload, "content", None)
        
        story = Story(
            user_id=current_user.id,
            username=current_user.username,
            media_url=media_url,
            media_type="text",
            caption=caption_val,
            audience=normalize_audience(getattr(payload, "audience", "PUBLIC"), is_admin=current_user.is_admin),
            created_at=now_naive,
            expires_at=expires_naive,
            music_id=resolved_music_id,
            music_title=getattr(payload, "music_title", None),
            music_artist=getattr(payload, "music_artist", None),
            music_url=getattr(payload, "music_url", None),
            music_thumbnail=getattr(payload, "music_thumbnail", None),
            music_duration=getattr(payload, "music_duration", 60.0) or 60.0,
            music_start_time=max(0.0, float(getattr(payload, "music_start_time", 0.0) or 0.0)),
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        process_and_create_mentions(db, story, getattr(payload, "mentions", None), caption_val, current_user)
        return build_story_item(story, current_user.id, db)

    @staticmethod
    async def upload_single_story(
        file: UploadFile,
        caption: Optional[str],
        audience: Optional[str],
        music_data: Optional[str],
        current_user: User,
        db: Session,
        music_start_time: Optional[float] = 0.0,
    ) -> StoryItemResponse:
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
            username=current_user.username,
            media_url=data_url,
            media_type=media_type,
            caption=caption,
            audience=normalize_audience(audience, is_admin=current_user.is_admin),
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
        process_and_create_mentions(db, story, None, caption, current_user)
        logger.info("Story %s uploaded by user %s to MySQL demousertable", story.story_id, current_user.id)
        return build_story_item(story, current_user.id, db)

    @staticmethod
    async def upload_multiple_stories(
        files: List[UploadFile],
        captions: Optional[str],
        audience: Optional[str],
        music_data: Optional[str],
        current_user: User,
        db: Session,
        music_start_time: Optional[float] = 0.0,
    ) -> StoryBatchResponse:
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
                username=current_user.username,
                media_url=data_url,
                media_type=media_type,
                caption=item_caption,
                audience=normalize_audience(audience, is_admin=current_user.is_admin),
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
            process_and_create_mentions(db, s, None, s.caption, current_user)

        items = [build_story_item(s, current_user.id, db) for s in created_stories]
        return StoryBatchResponse(
            success=True,
            message=f"Successfully published {len(created_stories)} stories to MySQL.",
            total_published=len(created_stories),
            stories=items,
        )

    @staticmethod
    def edit_story(story_id: int, caption: Optional[str], audience: Optional[Any], current_user: User, db: Session) -> StoryItemResponse:
        story = db.get(Story, story_id)
        if not story or story.is_deleted:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the story owner can edit it.")

        if caption is not None:
            story.caption = caption
        if audience is not None:
            story.audience = normalize_audience(audience, is_admin=current_user.is_admin)

        db.commit()
        db.refresh(story)
        return build_story_item(story, current_user.id, db)

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

        now_naive = make_naive(utc_now())
        story.is_deleted = True
        story.deleted_at = now_naive
        story.status = "deleted"

        derived_stories = db.query(Story).filter(
            or_(
                Story.original_story_id == story_id,
                Story.parent_story_id == story_id,
            ),
            Story.is_deleted == False,
        ).all()
        for ds in derived_stories:
            ds.is_deleted = True
            ds.deleted_at = now_naive
            ds.status = "deleted"

        db.commit()
        logger.info("Story %s (and %s derived stories) deleted by user %s", story_id, len(derived_stories), current_user.id)
        return {"success": True, "message": "Story deleted successfully", "story_id": story_id}

    @staticmethod
    def reshare_story(
        story_id: int,
        payload: Optional[StoryReshareRequest],
        current_user: User,
        db: Session,
    ) -> StoryItemResponse:
        source_story = db.get(Story, story_id)
        if not source_story or source_story.is_deleted:
            raise HTTPException(status_code=404, detail="Story not found or has been deleted.")

        now_naive = make_naive(utc_now())
        if source_story.expires_at and source_story.expires_at <= now_naive:
            raise HTTPException(status_code=400, detail="Cannot re-share an expired story.")

        if source_story.original_story_id and source_story.original_story_id != source_story.story_id:
            root_story = db.get(Story, source_story.original_story_id)
            if not root_story or root_story.is_deleted:
                raise HTTPException(status_code=400, detail="Cannot re-share: original story was deleted.")
            if root_story.expires_at and root_story.expires_at <= now_naive:
                raise HTTPException(status_code=400, detail="Cannot re-share: original story has expired.")
            orig_story_id = root_story.story_id
            orig_owner_id = root_story.user_id
        else:
            orig_story_id = source_story.story_id
            orig_owner_id = source_story.user_id

        for check_uid in {orig_owner_id, source_story.user_id}:
            if check_uid and check_uid != current_user.id:
                is_blocked = db.query(UserBlock).filter(
                    or_(
                        and_(UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == check_uid),
                        and_(UserBlock.blocker_id == check_uid, UserBlock.blocked_id == current_user.id),
                    )
                ) .first() is not None
                if is_blocked:
                    raise HTTPException(status_code=403, detail="Cannot re-share this story due to privacy/block restrictions.")

        has_mention = db.query(StoryMention).filter(
            StoryMention.story_id == source_story.story_id,
            StoryMention.mentioned_user_id == current_user.id,
        ).first() is not None

        if not has_mention and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RESHARE_NOT_ALLOWED: You can only re-share stories where you were explicitly mentioned."
            )

        existing_active_reshare = db.query(Story.story_id).filter(
            Story.user_id == current_user.id,
            or_(
                Story.parent_story_id == source_story.story_id,
                Story.original_story_id == orig_story_id,
            ),
            Story.is_deleted == False,
            Story.expires_at > now_naive,
        ).first()

        if existing_active_reshare:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ALREADY_RESHARED: You already have this mentioned story active on your profile. You can only re-share it again after deleting your active story.",
            )

        new_caption = getattr(payload, "caption", None) if payload else None
        if new_caption is None:
            new_caption = getattr(payload, "content", None) if payload else None
        if new_caption is None:
            new_caption = source_story.caption

        audience = normalize_audience(getattr(payload, "audience", "PUBLIC") if payload else "PUBLIC", is_admin=current_user.is_admin)

        new_story = Story(
            user_id=current_user.id,
            username=current_user.username,
            media_url=source_story.media_url,
            media_type=source_story.media_type,
            caption=new_caption,
            audience=audience,
            parent_story_id=source_story.story_id,
            original_story_id=orig_story_id,
            original_owner_id=orig_owner_id,
            status="active",
            created_at=now_naive,
            expires_at=now_naive + timedelta(hours=DEFAULT_DURATION_HOURS),
            music_id=source_story.music_id,
            music_title=source_story.music_title,
            music_artist=source_story.music_artist,
            music_url=source_story.music_url,
            music_thumbnail=source_story.music_thumbnail,
            music_duration=source_story.music_duration,
            music_start_time=source_story.music_start_time,
        )
        db.add(new_story)
        db.commit()
        db.refresh(new_story)

        if orig_owner_id and orig_owner_id != current_user.id:
            db.add(
                Notification(
                    user_id=orig_owner_id,
                    type="STORY_SHARED",
                    message=f"{current_user.username} shared your story",
                    reference_id=new_story.story_id,
                    is_read=False,
                    created_at=now_naive,
                )
            )
            db.commit()

        mentions_input = getattr(payload, "mentions", None) if payload else None
        if mentions_input:
            process_and_create_mentions(db, new_story, mentions_input, None, current_user)

        return build_story_item(new_story, current_user.id, db)
