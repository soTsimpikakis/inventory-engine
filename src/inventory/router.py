from fastapi import APIRouter
from models import InventoryItem
import service

router = APIRouter()


@router.get("/")
async def list_items(skip: int = 0, limit: int = 0):
    return {"skip": skip, "limit": limit, "items": []}


@router.get("/{product_id}")
async def get_item(product_id: str):
    return await service.get_item(product_id)


@router.post("/", status_code=201, response_model=InventoryItem)
async def create_item(item: InventoryItem):
    result = await service.create_item(item)
    return result
