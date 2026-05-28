"""
Milestone 5 — Security Validation Tests

Covers:
  - Unauthenticated requests → 401 Unauthorized
  - Invalid / tampered tokens → 401 Unauthorized
  - Valid token with wrong scope or role → 403 Forbidden
  - Valid token with mismatched tenant_id → 403 Forbidden
"""

from tests.conftest import make_m2m_token, make_user_token

BASE_URL = "/api/v1/inventory"
TENANT_A = "tenant_alpha"
TENANT_B = "tenant_beta"

# Pre-built payloads used across multiple tests
BULK_SYNC_BODY = {
    "idempotency_key": "auth-test-key",
    "tenant_id": TENANT_A,
    "items": [{"product_id": "auth_prod", "sku": "AUTH-SKU", "quantity": 10}],
}
RESERVE_BODY = {
    "tenant_id": TENANT_A,
    "product_id": "auth_prod",
    "user_id": "user_test",
    "quantity_requested": 1,
}


# ---------------------------------------------------------------------------
# 401 — No token
# ---------------------------------------------------------------------------

async def test_bulk_sync_no_token_returns_401(client):
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY)
    assert resp.status_code == 401


async def test_analytics_no_token_returns_401(client):
    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT_A})
    assert resp.status_code == 401


async def test_reserve_no_token_returns_401(client):
    resp = await client.post(f"{BASE_URL}/reserve", json=RESERVE_BODY)
    assert resp.status_code == 401


async def test_list_items_no_token_returns_401(client):
    resp = await client.get(f"{BASE_URL}/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 401 — Malformed / tampered token
# ---------------------------------------------------------------------------

async def test_malformed_token_returns_401(client):
    headers = {"Authorization": "Bearer this.is.not.a.valid.jwt"}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY, headers=headers)
    assert resp.status_code == 401


async def test_wrong_signature_returns_401(client):
    # Token signed with a different secret
    from jose import jwt as jose_jwt
    token = jose_jwt.encode(
        {"grant_type": "client_credentials", "scopes": ["inventory:write"], "tenant_id": TENANT_A},
        "wrong-secret",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY, headers=headers)
    assert resp.status_code == 401


async def test_bearer_prefix_missing_returns_401(client):
    token = make_m2m_token(TENANT_A)
    headers = {"Authorization": token}   # missing "Bearer " prefix
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY, headers=headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 403 — Valid token, wrong scope or role
# ---------------------------------------------------------------------------

async def test_user_token_on_bulk_sync_returns_403(client):
    """Interactive user tokens must not be accepted on the M2M-only /bulk-sync endpoint."""
    headers = {"Authorization": f"Bearer {make_user_token(TENANT_A)}"}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY, headers=headers)
    assert resp.status_code == 403


async def test_m2m_token_missing_inventory_write_scope_on_bulk_sync_returns_403(client):
    token = make_m2m_token(TENANT_A, scopes=["inventory:read"])
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY, headers=headers)
    assert resp.status_code == 403


async def test_m2m_token_on_analytics_returns_403(client):
    """M2M tokens do not carry the merchant_admin role required by /analytics."""
    headers = {"Authorization": f"Bearer {make_m2m_token(TENANT_A)}"}
    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT_A}, headers=headers)
    assert resp.status_code == 403


async def test_user_token_wrong_role_on_analytics_returns_403(client):
    token = make_user_token(TENANT_A, role="viewer")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT_A}, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 403 — Cross-tenant access (token tenant != request tenant)
# ---------------------------------------------------------------------------

async def test_cross_tenant_bulk_sync_returns_403(client):
    """M2M token scoped to TENANT_A must not be used to write TENANT_B data."""
    headers = {"Authorization": f"Bearer {make_m2m_token(TENANT_A)}"}
    body = {**BULK_SYNC_BODY, "tenant_id": TENANT_B, "idempotency_key": "cross-bulk-key"}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=body, headers=headers)
    assert resp.status_code == 403


async def test_cross_tenant_analytics_returns_403(client):
    """User token scoped to TENANT_A must not be used to read TENANT_B analytics."""
    headers = {"Authorization": f"Bearer {make_user_token(TENANT_A)}"}
    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT_B}, headers=headers)
    assert resp.status_code == 403


async def test_cross_tenant_reserve_returns_403(client):
    """Any valid token scoped to TENANT_A must not be used to reserve TENANT_B stock."""
    headers = {"Authorization": f"Bearer {make_user_token(TENANT_A)}"}
    body = {**RESERVE_BODY, "tenant_id": TENANT_B}
    resp = await client.post(f"{BASE_URL}/reserve", json=body, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 200 — Positive auth cases (token accepted, correct role/scope)
# ---------------------------------------------------------------------------

async def test_admin_role_token_accepted_on_bulk_sync(client):
    """An admin role token bypasses the M2M scope requirement on /bulk-sync."""
    from jose import jwt as jose_jwt
    from src.config import settings

    token = jose_jwt.encode(
        {"role": "admin", "tenant_id": TENANT_A},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"{BASE_URL}/bulk-sync",
        json={**BULK_SYNC_BODY, "idempotency_key": "admin-override-key"},
        headers=headers,
    )
    assert resp.status_code == 200


async def test_valid_m2m_token_accepted_on_bulk_sync(client):
    headers = {"Authorization": f"Bearer {make_m2m_token(TENANT_A)}"}
    resp = await client.post(f"{BASE_URL}/bulk-sync", json=BULK_SYNC_BODY, headers=headers)
    assert resp.status_code == 200


async def test_valid_merchant_admin_token_accepted_on_analytics(client):
    headers = {"Authorization": f"Bearer {make_user_token(TENANT_A)}"}
    resp = await client.get(f"{BASE_URL}/analytics", params={"tenant_id": TENANT_A}, headers=headers)
    assert resp.status_code == 200
