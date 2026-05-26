
from fastapi import APIRouter, Depends, Request
from .models import InventoryItem
from .service import InventoryService, get_db


router = APIRouter()



@router.get("/", response_model=list[InventoryItem])
async def list_items(skip: int = 0, limit: int = 100, db=Depends(get_db)):
    service = InventoryService(db)
    return await service.list_items(skip=skip, limit=limit)



@router.get("/{product_id}", response_model=InventoryItem)
async def get_item(product_id: str, db=Depends(get_db)):
    service = InventoryService(db)
    return await service.get_item(product_id)



@router.post("/", status_code=201, response_model=InventoryItem)
async def create_item(item: InventoryItem, db=Depends(get_db)):
    service = InventoryService(db)
    return await service.create_item(item)
