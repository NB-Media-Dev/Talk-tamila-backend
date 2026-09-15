from fastapi import APIRouter

router = APIRouter(prefix="/superadmin", tags=["Superadmin"])


@router.get("/health")
def superadmin_health():
    return {"status": "ok", "role": "superadmin"}
