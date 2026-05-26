
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_items(skip: int =0, limit: int = 0):
    return {
        "skip": skip,
        "limit": limit,
        "items": []
    }
    
@router.get('/{product_id}')
async def get_item(product_id: str):
    return {"product_id": product_id }