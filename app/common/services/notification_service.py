from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.common.models.social import Notification
from app.common.schemas.social import NotificationResponse


class NotificationService:
    @staticmethod
    def get_user_notifications(user_id: int, db: Session, limit: int = 20) -> List[NotificationResponse]:
        notifs = (
            db.query(Notification)
            .filter(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
            .all()
        )
        return [
            NotificationResponse(
                id=n.id,
                user_id=n.user_id,
                type=n.type,
                message=n.message,
                reference_id=n.reference_id,
                is_read=n.is_read,
                created_at=n.created_at.isoformat() if n.created_at else "",
            )
            for n in notifs
        ]
