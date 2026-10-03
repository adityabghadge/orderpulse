from fastapi import APIRouter

from app.api.routes import customers, orders

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(orders.router)
api_router.include_router(customers.router)
