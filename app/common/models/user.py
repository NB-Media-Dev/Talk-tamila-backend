from sqlalchemy import Column, Integer, String, Date, DateTime, Enum, Text
from sqlalchemy.sql import func
from app.core.database import Base
from app.common.enums import UserRole

class User(Base):
    __tablename__="users"

    user_id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String(100), unique=True, nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    mobile_no = Column(String(20), nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    dob = Column(Date, nullable=True)
    bio = Column(Text, nullable=True)
    profile_pic_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())