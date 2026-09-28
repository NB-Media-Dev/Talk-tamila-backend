from fastapi import APIRouter

router = APIRouter(prefix="/superadmin", tags=["Superadmin"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}

