from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.cache import get_cache
from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> JSONResponse:
    """Readiness check used by Docker and Kubernetes.

    The database is required; the cache is not. If Redis is down the API keeps serving from
    the database, so it reports the cache as unavailable but stays healthy.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"

    healthy = database == "ok"
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if healthy else "degraded",
            "database": database,
            "cache": "ok" if get_cache().ping() else "unavailable",
        },
    )
