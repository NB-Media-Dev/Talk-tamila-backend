from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token
from app.models.user import User
from app.schemas.auth import TokenOut, RegisterIn
from app.schemas.user import UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, details="Username already taken")

    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if db.query(User).filter(User.email == payload.email).first():
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

    return UserOut.from_orm_user(new_user)

@router.post("/login", response_model=TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub":str(user.user_id), "role": user.role.value})

    return TokenOut(
        access_token=access_token,
        token_type="bearer",
        user=UserOut.from_orm_user(user),
    )