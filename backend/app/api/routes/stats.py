from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stats import OverviewStats
from app.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
def overview(db: Annotated[Session, Depends(get_db)]) -> OverviewStats:
    """Headline numbers for the operations dashboard."""
    return stats_service.overview(db)
