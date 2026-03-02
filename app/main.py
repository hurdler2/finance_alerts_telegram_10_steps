from contextlib import asynccontextmanager

import stripe
from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.health import router as health_router
from app.api.admin import router as admin_router
from app.api.stripe_webhook import router as stripe_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
    yield


app = FastAPI(
    title="Finance Alerts API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(admin_router, prefix="/admin")
app.include_router(stripe_router)
