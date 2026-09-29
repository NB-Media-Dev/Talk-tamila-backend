from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.models.user import User
from app.common.schemas.messaging import MessageCreate, ReactionRequest
from app.common.services.message_service import MessageService
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get("/summary")
def summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Tiny payload polled by the navbar badge and the inbox."""
    return MessageService.summary(db, current_user)


@router.get("/conversations")
def conversations(
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return MessageService.conversations(db, current_user, limit)


@router.get("/users")
def people(
    q: str = Query("", max_length=100),
    limit: int = Query(30, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Everyone except me (with follow state) - powers "See all" and "New message"."""
    return MessageService.search_people(db, current_user, q, limit, offset)


@router.get("/thread/{user_id}")
def get_thread(
    user_id: int,
    after_id: Optional[int] = Query(None, ge=0),
    before_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(40, ge=1, le=100),
    sync_from_id: Optional[int] = Query(None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return MessageService.thread(
        db, current_user, user_id, after_id, before_id, limit, sync_from_id
    )


@router.post("/thread/{user_id}", status_code=status.HTTP_201_CREATED)
def send_message(
    user_id: int,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return MessageService.send(db, current_user, user_id, payload.body)


@router.post("/thread/{user_id}/read")
def mark_thread_read(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark this conversation as read from the inbox 3-dot menu (no need to open it)."""
    return MessageService.mark_read(db, current_user, user_id)


@router.post("/thread/{user_id}/unread")
def mark_thread_unread(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark this conversation as unread from the inbox 3-dot menu."""
    return MessageService.mark_unread(db, current_user, user_id)


@router.delete("/thread/{user_id}")
def delete_thread(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Delete this chat for me only (Instagram-style). The other person keeps theirs."""
    return MessageService.delete_chat(db, current_user, user_id)


@router.put("/{message_id}/reaction")
def react_to_message(
    message_id: int,
    payload: ReactionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """React to any message in one of my chats - sent or received. Replaces my previous reaction."""
    return MessageService.react(db, current_user, message_id, payload.emoji)


@router.delete("/{message_id}/reaction")
def remove_message_reaction(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return MessageService.unreact(db, current_user, message_id)


@router.delete("/{message_id}")
def unsend_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Unsend (delete for everyone) a message I sent."""
    return MessageService.unsend(db, current_user, message_id)