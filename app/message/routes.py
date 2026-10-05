import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.common.models.user import User
from app.common.schemas.messaging import MessageCreate, ReactionRequest
from app.common.services import push_service
from app.common.services.message_service import MessageService
from app.common.services.push_service import PushService
from app.core.config import settings
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/messages", tags=["Messages"])


class ReportUserRequest(BaseModel):
    reason: str = Field("", max_length=500)


class PushKeys(BaseModel):
    p256dh: str = Field(..., min_length=1, max_length=255)
    auth: str = Field(..., min_length=1, max_length=255)


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=750)
    keys: PushKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=750)


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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_push_endpoint: Optional[str] = Header(default=None),
) -> dict:
    message = MessageService.send(db, current_user, user_id, payload.body)
    # Instagram-style notification for the receiver. Runs after the response is sent,
    # so sending a message never gets slower, and never fails because of a notification.
    # x_push_endpoint = the sender's own browser, so it is never notified about its own message.
    background_tasks.add_task(PushService.notify_new_message, message["id"], x_push_endpoint)
    return message


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


@router.post("/thread/{user_id}/accept")
def accept_message_request(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Accept a message request: the chat moves from Requests to the main inbox."""
    return MessageService.accept_request(db, current_user, user_id)


@router.delete("/thread/{user_id}")
def delete_thread(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Delete this chat for me only (Instagram-style). The other person keeps theirs."""
    return MessageService.delete_chat(db, current_user, user_id)


@router.post("/thread/{user_id}/block")
def block_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Block this person: neither of you can message or call the other."""
    return MessageService.block(db, current_user, user_id)


@router.delete("/thread/{user_id}/block")
def unblock_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return MessageService.unblock(db, current_user, user_id)


@router.post("/thread/{user_id}/mute")
def mute_chat(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mute this chat: it stops counting in the unread badge."""
    return MessageService.mute(db, current_user, user_id)


@router.delete("/thread/{user_id}/mute")
def unmute_chat(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return MessageService.unmute(db, current_user, user_id)


@router.post("/thread/{user_id}/report", status_code=status.HTTP_201_CREATED)
def report_user(
    user_id: int,
    payload: ReportUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return MessageService.report(db, current_user, user_id, payload.reason)


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


# ---------- message notifications (Web Push) ----------
@router.get("/push/public-key")
def push_public_key(current_user: User = Depends(get_current_user)) -> dict:
    """The website asks this before offering "Turn on notifications"."""
    return {
        "enabled": push_service.is_configured(),
        "public_key": settings.VAPID_PUBLIC_KEY if push_service.is_configured() else "",
    }


@router.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
def push_subscribe(
    payload: PushSubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Save this browser so it receives message notifications for the logged-in user."""
    if not push_service.is_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Notifications are not set up on the server.")
    if not push_service.is_allowed_endpoint(payload.endpoint):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported notification address.")
    PushService.subscribe(db, current_user, payload.endpoint, payload.keys.p256dh, payload.keys.auth)
    return {"success": True}


@router.post("/push/unsubscribe")
async def push_unsubscribe(request: Request, db: Session = Depends(get_db)) -> dict:
    """Stop notifications for one browser (called when the person logs out).

    Deliberately needs no login token: the website calls it with navigator.sendBeacon
    at the moment of logout, when the token is already being thrown away. The
    `endpoint` is a long private address only that browser and this server know, so it
    works like a password for that one device and nothing else.
    """
    try:
        raw = await request.body()
        data = PushUnsubscribeRequest(**json.loads(raw or b"{}"))
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid request.")
    return {"success": True, "removed": PushService.unsubscribe(db, data.endpoint)}