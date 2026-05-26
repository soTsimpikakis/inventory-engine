
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_items():
    return {
        "items": []
    }
    
@router.get('/{product_id}')
async def get_item(product_id: str):
    return {"product_id": product_id }