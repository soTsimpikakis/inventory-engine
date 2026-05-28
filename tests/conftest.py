import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from jose import jwt as jose_jwt
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, IndexModel

from src.config import settings

TEST_DB_NAME = "test_inventory_db"


# ---------------------------------------------------------------------------
# Token factories — plain functions, not fixtures, so any test module can
# import and call them to build Authorization headers.
# ---------------------------------------------------------------------------

def make_m2m_token(tenant_id: str, scopes: list[str] | None = None) -> str:
    payload = {
        "grant_type": "client_credentials",
        "scopes": scopes or ["inventory:write"],
        "tenant_id": tenant_id,
    }
    return jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def make_user_token(
    tenant_id: str, role: str = "merchant_admin", sub: str = "user_test"
) -> str:
    payload = {"sub": sub, "role": role, "tenant_id": tenant_id}
    return jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest_asyncio.fixture
async def db():
    """
    Provides a clean Motor database for each test.
    Creates required indexes on setup; wipes all documents on teardown.
    """
    mc = AsyncIOMotorClient(settings.mongodb_uri)
    _db = mc[TEST_DB_NAME]

    await _db["inventory"].create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("product_id", ASCENDING)], unique=True),
        IndexModel([("tenant_id", ASCENDING)]),
        IndexModel([("sku", ASCENDING)]),
    ])
    await _db["idempotency_keys"].create_indexes([
        IndexModel([("idempotency_key", ASCENDING)], unique=True),
        IndexModel([("created_at", ASCENDING)], expireAfterSeconds=86400),
    ])

    yield _db

    await _db["inventory"].delete_many({})
    await _db["idempotency_keys"].delete_many({})
    mc.close()


@pytest_asyncio.fixture
async def client(db):
    """
    Provides an httpx AsyncClient wired to the FastAPI app with the test database injected.
    The app lifespan is NOT triggered; app.state.db is set directly so all service
    calls operate against the isolated test database.
    """
    from src.main import app

    app.state.db = db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
