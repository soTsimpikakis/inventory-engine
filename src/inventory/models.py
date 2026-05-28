from pydantic import BaseModel


class BulkSyncItem(BaseModel):
    product_id: str
    sku: str
    quantity: int
 
 
class BulkSyncRequest(BaseModel):
    idempotency_key: str
    tenant_id: str
    items: list[BulkSyncItem]
 
 
class BulkSyncResponse(BaseModel):
    idempotency_key: str
    tenant_id: str
    processed: int

class ReserveRequest(BaseModel):
    tenant_id: str
    product_id: str
    user_id: str
    quantity_requested: int
 
 
class ReserveResponse(BaseModel):
    product_id: str
    tenant_id: str
    quantity_reserved: int
    remaining_quantity: int