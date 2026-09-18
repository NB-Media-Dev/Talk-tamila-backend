from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.common.models.user import User
from app.common.schemas.auth import RegisterIn
from app.common.schemas.user import UserOut
from app.core.security import hash_password, verify_password, create_access_token

def register_user(db: Session, payload: RegisterIn) -> User:
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.mobile_no == payload.mobile_no).first():
        raise HTTPException(status_code=400, detail="Mobile number already registered")

    new_user = User(
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        mobile_no=payload.mobile_no,
        password=hash_password(payload.password),
        role=payload.role,
        dob=payload.dob,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return user

def login_user(db: Session, username: str, password: str) -> dict:
    user = authenticate_user(db, username, password)
    access_token = create_access_token(data={"sub": str(user.user_id), "role": user.role.value})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user),
    }