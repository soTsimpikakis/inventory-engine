from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.auth import (
    TokenClaims,
    get_current_token,
    require_m2m_write,
    require_merchant_admin,
    verify_tenant_access,
)
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


# /analytics must be declared before /{product_id} so the literal segment matches first.
@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    tenant_id: str = Query(..., description="Tenant identifier"),
    low_stock_threshold: int = Query(
        10, ge=0, description="Items at or below this quantity are flagged as low stock"
    ),
    token: Annotated[TokenClaims, Depends(require_merchant_admin)] = None,
    service: InventoryService = Depends(get_inventory_service),
):
    verify_tenant_access(token, tenant_id)
    return await service.get_analytics(
        tenant_id=tenant_id,
        low_stock_threshold=low_stock_threshold,
    )


@router.get("/", response_model=list[BulkSyncItem])
async def list_items(
    skip: int = 0,
    limit: int = 100,
    token: Annotated[TokenClaims, Depends(get_current_token)] = None,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.list_items(skip=skip, limit=limit)


@router.get("/{product_id}", response_model=BulkSyncItem)
async def get_item(
    product_id: str,
    token: Annotated[TokenClaims, Depends(get_current_token)] = None,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.get_item(product_id)


@router.post("/", status_code=201, response_model=BulkSyncItem)
async def create_item(
    item: BulkSyncItem,
    token: Annotated[TokenClaims, Depends(get_current_token)] = None,
    service: InventoryService = Depends(get_inventory_service),
):
    return await service.create_item(item)


@router.post("/bulk-sync", response_model=BulkSyncResponse, status_code=200)
async def bulk_sync(
    payload: BulkSyncRequest,
    token: Annotated[TokenClaims, Depends(require_m2m_write)] = None,
    service: InventoryService = Depends(get_inventory_service),
):
    verify_tenant_access(token, payload.tenant_id)
    return await service.bulk_sync(payload)


@router.post("/reserve", response_model=ReserveResponse, status_code=200)
async def reserve(
    payload: ReserveRequest,
    token: Annotated[TokenClaims, Depends(get_current_token)] = None,
    service: InventoryService = Depends(get_inventory_service),
):
    verify_tenant_access(token, payload.tenant_id)
    return await service.reserve(payload)
