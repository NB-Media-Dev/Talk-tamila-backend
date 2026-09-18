from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt
from app.core.config import settings

pwd_context = CryptContext(schemas=["bcrypt"],deprecated="auto")

def hash_password(plain_password: str):
    return pwd_context.hash(plain_password)

def verify_passowrd(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data:dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc)+ timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECERET_KEY, algorithm = settings.ALGORITHM)

def decode_access_token(token: str):
    return jwt.decode(token,settings.SECERET_KEY,algorithms=[settings.AGORITHM])