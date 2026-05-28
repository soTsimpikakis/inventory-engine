from typing import Annotated

from pydantic import BaseModel, Field


class BulkSyncItem(BaseModel):
    product_id: str
    sku: str
    quantity: Annotated[int, Field(ge=0)]


class BulkSyncRequest(BaseModel):
    idempotency_key: str
    tenant_id: str
    items: list[BulkSyncItem]


class BulkSyncResponse(BaseModel):
    idempotency_key: str
    tenant_id: str
    processed: int
    cached: bool = False


class ReserveRequest(BaseModel):
    tenant_id: str
    product_id: str
    user_id: str
    quantity_requested: Annotated[int, Field(gt=0)]


class ReserveResponse(BaseModel):
    product_id: str
    tenant_id: str
    quantity_reserved: int
    remaining_quantity: int


class LowStockItem(BaseModel):
    product_id: str
    sku: str
    quantity: int


class AnalyticsResponse(BaseModel):
    tenant_id: str
    total_skus: int
    total_quantity: int
    low_stock_count: int
    low_stock_items: list[LowStockItem]