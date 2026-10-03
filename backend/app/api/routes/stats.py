from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stats import OverviewStats
from app.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
def overview(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict:
    """Headline numbers for the operations dashboard.

    Served from Redis when cached (`X-Cache: HIT`), otherwise computed from precomputed daily
    totals plus today's live data (`X-Cache: MISS`).
    """
    payload, hit = stats_service.cached_overview(db)
    response.headers["X-Cache"] = "HIT" if hit else "MISS"
    return payload
