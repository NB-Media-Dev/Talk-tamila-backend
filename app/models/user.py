from sqlalchemy import Column, Integer , String, Date, DateTime, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import enum

class UserRole(str, enum.Enum):
    admin = "admin"
    influencer = "influencer"
    freelancer = "freelancer"

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100),unique=True, nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(100), unique = True, nullable=False, index=True)
    mobile_no = Column(String(20), nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    dob = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now())