from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "Healthcare Platform API",
    }
