from models import InventoryItem
from fastapi import HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase


class InventoryService:
    def __init__(self, db: AsyncIOMotorDatabase = Depends(get_db)):
        self.db = db

    async def list_items(self, skip: int, limit: int) -> list[InventoryItem]:
        cursor = self.db["inventory"].find(
            {},
            {"_id": 0}
        ).skip(skip).limit(limit)
        return cursor.to_list(length=limit) 

    async def create_item(item: InventoryItem) -> InventoryItem:
        return item.model_dump()

    async def get_item(product_id: str) -> InventoryItem:
        if product_id not in fake_db:
            raise HTTPException(
                status_code=404, detail=f"Product '{product_id} not found"
            )

        return fake_db[product_id]
