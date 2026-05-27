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
