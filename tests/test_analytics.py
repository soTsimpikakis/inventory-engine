"""
Milestone 3 — Database Aggregation Analytics Engine
"""

from tests.conftest import make_m2m_token, make_user_token

TENANT = "tenant_analytics"
OTHER_TENANT = "tenant_other"
BASE_URL = "/api/v1/inventory"

# Analytics requires a merchant_admin user token.
USER_HEADERS = {"Authorization": f"Bearer {make_user_token(TENANT)}"}


async def seed_inventory(client, tenant: str, items: list[dict], key_suffix: str = "") -> None:
    # Each tenant's seed uses an M2M token scoped to that tenant.
    headers = {"Authorization": f"Bearer {make_m2m_token(tenant)}"}
    await client.post(
        f"{BASE_URL}/bulk-sync",
        json={
            "idempotency_key": f"analytics-seed-{tenant}-{key_suffix}",
            "tenant_id": tenant,
            "items": items,
        },
        headers=headers,
    )


async def test_analytics_empty_tenant_returns_zeros(client):
    headers = {"Authorization": f"Bearer {make_user_token('empty_tenant')}"}
    resp = await client.get(
        f"{BASE_URL}/analytics", params={"tenant_id": "empty_tenant"}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "empty_tenant"
    assert body["total_skus"] == 0
    assert body["total_quantity"] == 0
    assert body["low_stock_count"] == 0
    assert body["low_stock_items"] == []


async def test_analytics_total_skus_and_quantity(client):
    await seed_inventory(
        client,
        TENANT,
        [
            {"product_id": "p1", "sku": "SKU-1", "quantity": 100},
            {"product_id": "p2", "sku": "SKU-2", "quantity": 200},
            {"product_id": "p3", "sku": "SKU-3", "quantity": 50},
        ],
        key_suffix="totals",
    )

    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT}, headers=USER_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_skus"] == 3
    assert body["total_quantity"] == 350


async def test_analytics_low_stock_default_threshold(client):
    """Default threshold is 10 — items with quantity <= 10 appear in low_stock_items."""
    await seed_inventory(
        client,
        TENANT,
        [
            {"product_id": "p_high", "sku": "HIGH", "quantity": 500},
            {"product_id": "p_low", "sku": "LOW", "quantity": 5},
            {"product_id": "p_edge", "sku": "EDGE", "quantity": 10},
        ],
        key_suffix="threshold",
    )

    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT}, headers=USER_HEADERS)

    body = resp.json()
    low_ids = {item["product_id"] for item in body["low_stock_items"]}
    assert "p_low" in low_ids
    assert "p_edge" in low_ids   # exactly at threshold — must be included
    assert "p_high" not in low_ids
    assert body["low_stock_count"] == 2


async def test_analytics_custom_low_stock_threshold(client):
    await seed_inventory(
        client,
        TENANT,
        [
            {"product_id": "c1", "sku": "C1", "quantity": 100},
            {"product_id": "c2", "sku": "C2", "quantity": 60},
            {"product_id": "c3", "sku": "C3", "quantity": 30},
        ],
        key_suffix="custom",
    )

    resp = await client.get(
        f"{BASE_URL}/analytics",
        params={"tenant_id": TENANT, "low_stock_threshold": 50},
        headers=USER_HEADERS,
    )

    body = resp.json()
    low_ids = {item["product_id"] for item in body["low_stock_items"]}
    assert "c3" in low_ids
    assert "c2" not in low_ids
    assert "c1" not in low_ids


async def test_analytics_low_stock_items_sorted_by_quantity_ascending(client):
    await seed_inventory(
        client,
        TENANT,
        [
            {"product_id": "sort_3", "sku": "S3", "quantity": 8},
            {"product_id": "sort_1", "sku": "S1", "quantity": 2},
            {"product_id": "sort_2", "sku": "S2", "quantity": 5},
        ],
        key_suffix="sort",
    )

    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT}, headers=USER_HEADERS)

    low_items = resp.json()["low_stock_items"]
    quantities = [item["quantity"] for item in low_items]
    assert quantities == sorted(quantities), "Low-stock items must be sorted ascending by quantity"


async def test_analytics_tenant_isolation(client):
    """Analytics must only reflect the requested tenant's inventory."""
    await seed_inventory(
        client, TENANT, [{"product_id": "mine", "sku": "MINE", "quantity": 10}], key_suffix="iso_a"
    )
    await seed_inventory(
        client,
        OTHER_TENANT,
        [
            {"product_id": "theirs_1", "sku": "T1", "quantity": 999},
            {"product_id": "theirs_2", "sku": "T2", "quantity": 888},
        ],
        key_suffix="iso_b",
    )

    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT}, headers=USER_HEADERS)

    body = resp.json()
    assert body["total_skus"] == 1
    assert body["total_quantity"] == 10


async def test_analytics_missing_tenant_id_rejected(client):
    resp = await client.get(f"{BASE_URL}/analytics", headers=USER_HEADERS)
    assert resp.status_code == 422


async def test_analytics_negative_threshold_rejected(client):
    resp = await client.get(
        f"{BASE_URL}/analytics",
        params={"tenant_id": TENANT, "low_stock_threshold": -1},
        headers=USER_HEADERS,
    )
    assert resp.status_code == 422


async def test_analytics_route_not_swallowed_by_product_id_route(client):
    """
    Regression guard: GET /analytics must resolve to the analytics handler,
    not the /{product_id} handler (which would return 404 for unknown product).
    """
    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT}, headers=USER_HEADERS)
    assert resp.status_code == 200
    assert "total_skus" in resp.json()
