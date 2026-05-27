from datetime import datetime, UTC

from fastapi import HTTPException, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from .models import BulkSyncItem, BulkSyncRequest, BulkSyncResponse

class InventoryService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def list_items(self, skip: int = 0, limit: int = 100) -> list[BulkSyncItem]:
        cursor = self.db["inventory"].find({}, {"_id": 0})
        items = await cursor.skip(skip).limit(limit).to_list(length=limit)
        return [BulkSyncItem(**item) for item in items]

    async def create_item(self, item: BulkSyncItem) -> BulkSyncItem:
        await self.db["inventory"].insert_one(item.model_dump())
        return item

    async def get_item(self, product_id: str) -> BulkSyncItem:
        doc = await self.db["inventory"].find_one(
            {"product_id": product_id}, {"_id": 0}
        )
        if not doc:
            raise HTTPException(
                status_code=404, detail=f"Product '{product_id}' not found"
            )
        return BulkSyncItem(**doc)

    async def bulk_sync(self, payload: BulkSyncRequest) -> BulkSyncResponse:
        # Check idempotency key — return cached response if already processed
        existing = await self.db["idempotency_keys"].find_one(
            {"idempotency_key": payload.idempotency_key}
        )
        if existing:
            return BulkSyncResponse(**existing["response"])

        # Upsert each item: set sku and quantity, create doc if missing
        for item in payload.items:
            await self.db["inventory"].update_one(
                {
                    "tenant_id": payload.tenant_id,
                    "product_id": item.product_id,
                },
                {
                    "$set": {
                        "sku": item.sku,
                        "quantity": item.quantity,
                        "updated_at": datetime.now(UTC),
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(UTC),
                    },
                },
                upsert=True,
            )

        response = BulkSyncResponse(
            idempotency_key=payload.idempotency_key,
            tenant_id=payload.tenant_id,
            processed=len(payload.items),
            cached=False,
        )

        # Store idempotency key with the response so repeated calls return it
        await self.db["idempotency_keys"].insert_one(
            {
                "idempotency_key": payload.idempotency_key,
                "response": response.model_dump(),
                "created_at": datetime.now(UTC),
            }
        )

        return response


# Dependency to get the MongoDB database from FastAPI app state
def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


# Dependency to get the InventoryService with injected database
def get_inventory_service(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> InventoryService:
    return InventoryService(db)


