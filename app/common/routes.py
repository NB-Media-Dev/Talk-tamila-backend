from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Routes moved to main.py auth_router