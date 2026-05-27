from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from src.config import settings
from src.inventory.router import router as inventory_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.database_name]
    app.state.db = db

    # Indexes — created idempotently on every startup
    await db["inventory"].create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("product_id", ASCENDING)], unique=True),
        IndexModel([("tenant_id", ASCENDING)]),
        IndexModel([("sku", ASCENDING)]),
    ])
    await db["idempotency_keys"].create_indexes([
        IndexModel([("idempotency_key", ASCENDING)], unique=True),
        IndexModel([("created_at", ASCENDING)], expireAfterSeconds=86400),  # TTL: 24h
    ])

    yield

    client.close()


# def get_db(request: Request) -> AsyncIOMotorDatabase:
#     return request.app.state.db


def create_app() -> FastAPI:
    app = FastAPI(title="Inventory Engine", version="1.0.0", lifespan=lifespan)

    app.include_router(
        inventory_router,
        prefix="/api/v1/inventory",
        tags=["inventory"],
    )

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()