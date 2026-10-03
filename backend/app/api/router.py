from fastapi import APIRouter

from app.api.routes import customers, orders, returns, stats

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(orders.router)
api_router.include_router(returns.order_returns_router)
api_router.include_router(returns.router)
api_router.include_router(customers.router)
api_router.include_router(stats.router)
