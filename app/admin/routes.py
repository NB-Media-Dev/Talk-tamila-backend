from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, get_current_admin
from app.admin.services import AdminService
from app.common.models.user import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/overview")
def get_admin_overview(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return AdminService.get_overview(db)
