"""
Milestone 2 — Multi-Node Concurrency Engine (Allocations)

The race-condition test (test_no_oversell_under_concurrent_load) is the centrepiece:
it fires 50 parallel reservation requests against a product with exactly 10 units and
asserts that exactly 10 succeed and the final stock is exactly 0.
"""

import asyncio

from tests.conftest import make_m2m_token, make_user_token

TENANT = "tenant_reserve"
BASE_URL = "/api/v1/inventory"

# Seeding uses /bulk-sync (M2M); reservations use /reserve (any valid token).
M2M_HEADERS = {"Authorization": f"Bearer {make_m2m_token(TENANT)}"}
USER_HEADERS = {"Authorization": f"Bearer {make_user_token(TENANT)}"}


async def seed_product(client, product_id: str, quantity: int, sku: str = "TEST-SKU") -> None:
    await client.post(
        f"{BASE_URL}/bulk-sync",
        json={
            "idempotency_key": f"seed-{product_id}-{quantity}",
            "tenant_id": TENANT,
            "items": [{"product_id": product_id, "sku": sku, "quantity": quantity}],
        },
        headers=M2M_HEADERS,
    )


def reserve_payload(product_id: str, quantity: int = 1) -> dict:
    return {
        "tenant_id": TENANT,
        "product_id": product_id,
        "user_id": "user_test",
        "quantity_requested": quantity,
    }


async def test_reserve_success_returns_200_and_remaining(client):
    await seed_product(client, "prod_res_1", quantity=10)

    resp = await client.post(
        f"{BASE_URL}/reserve", json=reserve_payload("prod_res_1", quantity=3), headers=USER_HEADERS
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["product_id"] == "prod_res_1"
    assert body["tenant_id"] == TENANT
    assert body["quantity_reserved"] == 3
    assert body["remaining_quantity"] == 7


async def test_reserve_depletes_to_zero(client):
    await seed_product(client, "prod_res_deplete", quantity=5)

    resp = await client.post(
        f"{BASE_URL}/reserve",
        json=reserve_payload("prod_res_deplete", quantity=5),
        headers=USER_HEADERS,
    )

    assert resp.status_code == 200
    assert resp.json()["remaining_quantity"] == 0


async def test_reserve_insufficient_stock_returns_409(client):
    await seed_product(client, "prod_res_low", quantity=3)

    resp = await client.post(
        f"{BASE_URL}/reserve",
        json=reserve_payload("prod_res_low", quantity=5),
        headers=USER_HEADERS,
    )

    assert resp.status_code == 409


async def test_reserve_nonexistent_product_returns_409(client):
    resp = await client.post(
        f"{BASE_URL}/reserve", json=reserve_payload("ghost_product", quantity=1), headers=USER_HEADERS
    )
    assert resp.status_code == 409


async def test_reserve_rejects_zero_quantity(client):
    resp = await client.post(
        f"{BASE_URL}/reserve", json=reserve_payload("prod_any", quantity=0), headers=USER_HEADERS
    )
    assert resp.status_code == 422


async def test_reserve_rejects_negative_quantity(client):
    resp = await client.post(
        f"{BASE_URL}/reserve", json=reserve_payload("prod_any", quantity=-5), headers=USER_HEADERS
    )
    assert resp.status_code == 422


async def test_reserve_rejects_missing_tenant_id(client):
    resp = await client.post(
        f"{BASE_URL}/reserve",
        json={"product_id": "p", "user_id": "u", "quantity_requested": 1},
        headers=USER_HEADERS,
    )
    assert resp.status_code == 422


async def test_no_oversell_under_concurrent_load(client, db):
    """
    Milestone 5 requirement: initialise product with 10 units, fire 50 parallel
    reservation requests of 1 unit each.

    Expected outcome:
      - Exactly 10 requests receive HTTP 200 (stock exhausted after 10 fills)
      - Exactly 40 requests receive HTTP 409 (insufficient stock)
      - Final stock level is exactly 0 (no oversell, no underfill)
    """
    product_id = "race_product"
    initial_stock = 10
    concurrent_requests = 50

    await seed_product(client, product_id, quantity=initial_stock)

    async def reserve_one():
        return await client.post(
            f"{BASE_URL}/reserve",
            json=reserve_payload(product_id, quantity=1),
            headers=USER_HEADERS,
        )

    results = await asyncio.gather(*[reserve_one() for _ in range(concurrent_requests)])

    statuses = [r.status_code for r in results]
    successes = statuses.count(200)
    conflicts = statuses.count(409)

    assert successes == initial_stock, (
        f"Expected exactly {initial_stock} successful reservations, got {successes}"
    )
    assert conflicts == concurrent_requests - initial_stock, (
        f"Expected {concurrent_requests - initial_stock} conflicts, got {conflicts}"
    )

    doc = await db["inventory"].find_one({"tenant_id": TENANT, "product_id": product_id})
    assert doc["quantity"] == 0, (
        f"Stock must be exactly 0 after {initial_stock} successful reservations, got {doc['quantity']}"
    )
