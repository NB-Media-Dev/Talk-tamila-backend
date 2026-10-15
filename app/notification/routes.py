from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

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
    return NotificationService.get_notifications(current_user.user_id, db, limit)


@router.get("/unread-count", summary="Get count of unread notifications")
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return NotificationService.get_unread_count(current_user.user_id, db)


@router.patch("/{notification_id:int}/read", summary="Mark a notification as read")
@router.post("/{notification_id:int}/read", summary="Mark a notification as read")
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return NotificationService.mark_notification_read(current_user.user_id, notification_id, db)


@router.patch("/read-all", summary="Mark all notifications as read")
@router.post("/read-all", summary="Mark all notifications as read")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return NotificationService.mark_all_notifications_read(current_user.user_id, db)


@router.delete("/{notification_id:int}", summary="Delete a notification")
def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return NotificationService.delete_notification(current_user.user_id, notification_id, db)
