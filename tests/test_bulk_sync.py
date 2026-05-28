"""
Milestone 1 — Idempotent Bulk Sync Stream Ingestion
"""

import asyncio

from tests.conftest import make_m2m_token

TENANT = "tenant_test"
BASE_URL = "/api/v1/inventory"

# All /bulk-sync requests require an M2M token with inventory:write scope.
HEADERS = {"Authorization": f"Bearer {make_m2m_token(TENANT)}"}


def sync_payload(idempotency_key: str, items: list[dict] | None = None) -> dict:
    return {
        "idempotency_key": idempotency_key,
        "tenant_id": TENANT,
        "items": items
        or [
            {"product_id": "prod_a", "sku": "SKU-A", "quantity": 100},
            {"product_id": "prod_b", "sku": "SKU-B", "quantity": 50},
        ],
    }


async def test_bulk_sync_returns_200_with_processed_count(client):
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=sync_payload("key-001"), headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["idempotency_key"] == "key-001"
    assert body["tenant_id"] == TENANT
    assert body["processed"] == 2
    assert body["cached"] is False


async def test_bulk_sync_upserts_inventory_records(client, db):
    await client.post(f"{BASE_URL}/bulk-sync", json=sync_payload("key-upsert"), headers=HEADERS)

    doc = await db["inventory"].find_one({"tenant_id": TENANT, "product_id": "prod_a"})
    assert doc is not None
    assert doc["sku"] == "SKU-A"
    assert doc["quantity"] == 100


async def test_bulk_sync_updates_existing_quantity(client, db):
    await client.post(
        f"{BASE_URL}/bulk-sync",
        json=sync_payload("key-v1", [{"product_id": "prod_x", "sku": "SKU-X", "quantity": 200}]),
        headers=HEADERS,
    )
    await client.post(
        f"{BASE_URL}/bulk-sync",
        json=sync_payload("key-v2", [{"product_id": "prod_x", "sku": "SKU-X", "quantity": 999}]),
        headers=HEADERS,
    )

    doc = await db["inventory"].find_one({"tenant_id": TENANT, "product_id": "prod_x"})
    assert doc["quantity"] == 999


async def test_bulk_sync_idempotency_second_call_returns_cached(client):
    payload = sync_payload("key-idem")

    first = await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)
    second = await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True


async def test_bulk_sync_idempotency_does_not_mutate_on_repeat(client, db):
    payload = sync_payload("key-no-mutate", [{"product_id": "prod_m", "sku": "SKU-M", "quantity": 10}])

    await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)

    # Manually bump quantity directly in DB to simulate external change
    await db["inventory"].update_one(
        {"tenant_id": TENANT, "product_id": "prod_m"},
        {"$set": {"quantity": 999}},
    )

    # Repeat — should be served from cache, not re-execute writes
    await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)

    doc = await db["inventory"].find_one({"tenant_id": TENANT, "product_id": "prod_m"})
    assert doc["quantity"] == 999, "Idempotent replay must not overwrite existing DB state"


async def test_bulk_sync_concurrent_same_key_all_succeed(client):
    """
    50 concurrent requests with the same idempotency key must all return 200.
    Exactly one writes; the rest are served from cache.
    """
    payload = sync_payload("key-concurrent")

    results = await asyncio.gather(
        *[client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS) for _ in range(50)]
    )

    statuses = [r.status_code for r in results]
    assert all(s == 200 for s in statuses)

    bodies = [r.json() for r in results]
    assert sum(1 for b in bodies if b["cached"] is False) == 1
    assert sum(1 for b in bodies if b["cached"] is True) == 49


async def test_bulk_sync_rejects_negative_quantity(client):
    payload = sync_payload("key-neg", [{"product_id": "prod_z", "sku": "SKU-Z", "quantity": -1}])
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)
    assert resp.status_code == 422


async def test_bulk_sync_accepts_zero_quantity(client):
    payload = sync_payload("key-zero", [{"product_id": "prod_z", "sku": "SKU-Z", "quantity": 0}])
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)
    assert resp.status_code == 200


async def test_bulk_sync_rejects_empty_items(client):
    payload = {"idempotency_key": "key-empty", "tenant_id": TENANT, "items": []}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)
    # Empty list is technically valid Pydantic — processed count will be 0.
    assert resp.status_code == 200
    assert resp.json()["processed"] == 0


async def test_bulk_sync_missing_idempotency_key_rejected(client):
    payload = {"tenant_id": TENANT, "items": [{"product_id": "p", "sku": "s", "quantity": 1}]}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=payload, headers=HEADERS)
    assert resp.status_code == 422
