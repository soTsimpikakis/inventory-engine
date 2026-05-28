from fastapi import APIRouter, Depends, Query

from .models import (
    AnalyticsResponse,
    BulkSyncItem,
    BulkSyncRequest,
    BulkSyncResponse,
    ReserveRequest,
    ReserveResponse,
)
from .service import InventoryService, get_inventory_service

router = APIRouter()

@router.get("/", response_model=list[BulkSyncItem])
async def list_items(
    skip: int = 0,
    limit: int = 100,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.list_items(skip=skip, limit=limit)


@router.get("/{product_id}", response_model=BulkSyncItem)
async def get_item(
    product_id: str,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.get_item(product_id)


@router.post("/", status_code=201, response_model=BulkSyncItem)
async def create_item(
    item: BulkSyncItem,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.create_item(item)


@router.post("/bulk-sync", response_model=BulkSyncResponse, status_code=200)
async def bulk_sync(
    payload: BulkSyncRequest,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.bulk_sync(payload)


@router.post("/reserve", response_model=ReserveResponse, status_code=200)
async def reserve(
    payload: ReserveRequest,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.reserve(payload)



@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    tenant_id: str = Query(..., description="Tenant identifier"),
    low_stock_threshold: int = Query(
        10, ge=0, description="Items at or below this quantity are flagged as low stock"
    ),
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.get_analytics(
        tenant_id=tenant_id,
        low_stock_threshold=low_stock_threshold,
    )

