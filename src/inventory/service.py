from datetime import datetime, UTC

from fastapi import HTTPException, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError

from .models import (
    AnalyticsResponse,
    BulkSyncItem,
    BulkSyncRequest,
    BulkSyncResponse,
    LowStockItem,
    ReserveRequest,
    ReserveResponse,
)


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
        existing = await self.db["idempotency_keys"].find_one(
            {"idempotency_key": payload.idempotency_key}
        )
        if existing:
            return BulkSyncResponse(**{**existing["response"], "cached": True})

        now = datetime.now(UTC)
        operations = [
            UpdateOne(
                {"tenant_id": payload.tenant_id, "product_id": item.product_id},
                {
                    "$set": {
                        "sku": item.sku,
                        "quantity": item.quantity,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            for item in payload.items
        ]
        await self.db["inventory"].bulk_write(operations, ordered=False)

        response = BulkSyncResponse(
            idempotency_key=payload.idempotency_key,
            tenant_id=payload.tenant_id,
            processed=len(payload.items),
        )

        try:
            await self.db["idempotency_keys"].insert_one(
                {
                    "idempotency_key": payload.idempotency_key,
                    "response": response.model_dump(),
                    "created_at": now,
                }
            )
        except DuplicateKeyError:
            existing = await self.db["idempotency_keys"].find_one(
                {"idempotency_key": payload.idempotency_key}
            )
            return BulkSyncResponse(**{**existing["response"], "cached": True})

        return response

    async def reserve(self, payload: ReserveRequest) -> ReserveResponse:
        updated = await self.db["inventory"].find_one_and_update(
            {
                "tenant_id": payload.tenant_id,
                "product_id": payload.product_id,
                "quantity": {"$gte": payload.quantity_requested},
            },
            {
                "$inc": {"quantity": -payload.quantity_requested},
                "$set": {"updated_at": datetime.now(UTC)},
            },
            return_document=ReturnDocument.AFTER,
        )

        if updated is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Insufficient stock for product '{payload.product_id}'. "
                    "Requested quantity unavailable."
                ),
            )

        return ReserveResponse(
            product_id=payload.product_id,
            tenant_id=payload.tenant_id,
            quantity_reserved=payload.quantity_requested,
            remaining_quantity=updated["quantity"],
        )
        

    async def get_analytics(
        self, tenant_id: str, low_stock_threshold: int = 10
    ) -> AnalyticsResponse:
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {
                "$facet": {
                    "summary": [
                        {
                            "$group": {
                                "_id": None,
                                "total_skus": {"$sum": 1},
                                "total_quantity": {"$sum": "$quantity"},
                            }
                        }
                    ],
                    "low_stock": [
                        {"$match": {"quantity": {"$lte": low_stock_threshold}}},
                        {
                            "$project": {
                                "_id": 0,
                                "product_id": 1,
                                "sku": 1,
                                "quantity": 1,
                            }
                        },
                        {"$sort": {"quantity": 1}},
                    ],
                }
            },
        ]

        result = await self.db["inventory"].aggregate(pipeline).to_list(length=1)

        if not result:
            return AnalyticsResponse(
                tenant_id=tenant_id,
                total_skus=0,
                total_quantity=0,
                low_stock_count=0,
                low_stock_items=[],
            )

        data = result[0]
        summary = data["summary"][0] if data["summary"] else {"total_skus": 0, "total_quantity": 0}
        low_stock = data["low_stock"]

        return AnalyticsResponse(
            tenant_id=tenant_id,
            total_skus=summary["total_skus"],
            total_quantity=summary["total_quantity"],
            low_stock_count=len(low_stock),
            low_stock_items=[LowStockItem(**item) for item in low_stock],
        )


def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


def get_inventory_service(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> InventoryService:
    return InventoryService(db)
