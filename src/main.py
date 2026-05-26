from contextlib import asynccontextmanager

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, IndexModel

from src.config import settings
from src.inventory.router import router as inventory_router

# ── Database lifecycle ────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to MongoDB and ensure indexes exist on startup."""
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.database_name]

    app.state.db = db

    inventory = db["inventory"]
    await inventory.create_indexes(
        [
            IndexModel(
                [("tenant_id", ASCENDING), ("product_id", ASCENDING)], unique=True
            ),
            IndexModel([("tenant_id", ASCENDING)]),
            IndexModel([("sku", ASCENDING)]),
        ]
    )

    idempotency = db["idempotency_keys"]
    await idempotency.create_indexes(
        [
            IndexModel([("idempotency_key", ASCENDING)], unique=True),
            # TTL index: auto-expire keys after 24 h
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=86400),
        ]
    )

    yield

    client.close()


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="Inventory API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
