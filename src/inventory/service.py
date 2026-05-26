
from fastapi import HTTPException, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from .models import InventoryItem



# Dependency to get the MongoDB database from FastAPI app state
def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


class InventoryService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def list_items(self, skip: int = 0, limit: int = 100) -> list[InventoryItem]:
        cursor = self.db["inventory"].find({}, {"_id": 0})
        items = await cursor.skip(skip).limit(limit).to_list(length=limit)
        return [InventoryItem(**item) for item in items]

    async def create_item(self, item: InventoryItem) -> InventoryItem:
        await self.db["inventory"].insert_one(item.model_dump())
        return item

    async def get_item(self, product_id: str) -> InventoryItem:
        doc = await self.db["inventory"].find_one({"product_id": product_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
        return InventoryItem(**doc)
