from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.models.social import Notification
from app.common.models.user import User
from app.common.schemas.social import NotificationResponse
from app.common.services.notification_service import NotificationService
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationResponse], summary="Get current user's notifications")
def get_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return NotificationService.get_user_notifications(current_user.user_id, db, limit)


@router.get("/unread-count", summary="Get count of unread notifications")
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.user_id,
            Notification.is_read.is_(False),
        )
        .count()
    )
    return {"unread_count": count}


@router.patch("/{notification_id:int}/read", summary="Mark a notification as read")
@router.post("/{notification_id:int}/read", summary="Mark a notification as read")
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.user_id,
        )
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notif.is_read = True
    db.commit()
    return {"success": True}


@router.patch("/read-all", summary="Mark all notifications as read")
@router.post("/read-all", summary="Mark all notifications as read")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        Notification.is_read.is_(False),
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"success": True}


@router.delete("/{notification_id:int}", summary="Delete a notification")
def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.user_id,
        )
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found.")
    db.delete(notif)
    db.commit()
    return {"success": True}
