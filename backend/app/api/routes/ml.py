from fastapi import APIRouter

from app.ml.registry import model_summary

router = APIRouter(prefix="/ml", tags=["machine learning"])


@router.get("/models")
def models() -> dict:
    """Which models are loaded, when they were trained, and how they scored on held-out data."""
    return model_summary()
