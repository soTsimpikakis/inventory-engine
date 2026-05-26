from pydantic import BaseModel


class InventoryItem(BaseModel):
    product_id: str
    sku: str
    quantity: int
    tenant_id: str
