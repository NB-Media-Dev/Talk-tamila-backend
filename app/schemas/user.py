from pydantic import BaseModel
from datetime import date, datetime 
from app.models.user import UserRole

class UserOut(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
    mobile_no: str
    role: UserRole
    dob: date | None = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_user(cls, user):
        return cls(
            id=user.user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            mobile_no=user.mobile_no,
            role=user.role,
            dob=user.dob,
            created_at=user.created_at,
        )