# inventory-engine

High-Throughput Multi-Tenant Inventory Engine — FastAPI + MongoDB

---

## Architecture Decisions

### Idempotency (Milestone 1)

Duplicate protection is handled by a dedicated `idempotency_keys` MongoDB collection. On every `/bulk-sync` request, the service checks for an existing document matching the `idempotency_key` before executing any writes. If found, the cached response is returned immediately, bypassing the bulk-write pipeline entirely.

To guard against race conditions on the idempotency check itself (two identical requests arriving simultaneously), the insert is wrapped in a `DuplicateKeyError` catch — the unique index on `idempotency_key` makes concurrent inserts safe without any application-level locking. A 24-hour TTL index on `created_at` automatically expires stale keys.

### Concurrency & Stock Safety (Milestone 2)

Stock reservation uses a single atomic `findOneAndUpdate` with a filter that includes `"quantity": {"$gte": quantity_requested}`. MongoDB evaluates the filter and the decrement atomically — if the stock is insufficient the document is not modified and `None` is returned, which maps to HTTP 409.

This is a stateless, database-coordinated approach: no Python threading locks, no application-level counters. It scales horizontally because every app instance relies on the same MongoDB document-level concurrency guarantee.

### Analytics (Milestone 3)

The analytics endpoint uses a single aggregation pipeline with a `$facet` stage to compute the tenant summary (total SKU count, total quantity) and the low-stock list in one round trip. All computation is offloaded to MongoDB — the Python layer only serializes the result. This keeps the app stateless and the response latency proportional to database throughput, not Python CPU.

### Authentication (Milestone 4)

Two JWT token profiles are supported, both verified with HS256:

- **M2M tokens** (client credentials): must carry `"grant_type": "client_credentials"` and `"scopes": ["inventory:write"]`. Required on `/bulk-sync`.
- **User tokens** (interactive): must carry `"role": "merchant_admin"` and `"tenant_id"`. Required on `/analytics`.

Cross-tenant isolation is enforced at the route level via `verify_tenant_access`, which compares the `tenant_id` claim extracted from the token against the `tenant_id` in the request body or query parameter. A mismatch short-circuits with HTTP 403 before any database call is made.

---

## Verification Setup

**Prerequisites:** Docker and Docker Compose.

```bash
# Start MongoDB (replica set) and the API
docker compose up -d

# Run the full integration test suite inside the running container
docker compose exec app pytest -v
```

Tests use an isolated `test_inventory_db` database and clean up after each run. All four test modules (auth, bulk-sync, reserve, analytics) are covered, including the 50-concurrent-request race condition test.

---

## Scaling Vision (50x Traffic)

At 50x current load the bottlenecks shift from the app layer to data throughput and write fan-out. The changes below address each layer:

| Layer | Change | Reason |
|---|---|---|
| App | Horizontal scaling behind a load balancer | FastAPI is fully stateless; adding replicas is zero-config |
| Database | MongoDB sharded cluster (shard on `tenant_id`) | Distributes write load across shards; each tenant's data stays co-located |
| Idempotency cache | Redis in front of MongoDB for key lookups | Sub-millisecond read on the hot path; MongoDB becomes the durable fallback |
| Bulk ingest | Kafka / SQS between upstream producers and `/bulk-sync` | Absorbs write spikes without back-pressure on the API; enables replay on failure |
| Analytics | Cache aggregation responses in Redis with a short TTL (e.g. 30s) | Analytics data changes slowly; serving from cache removes aggregation cost from the hot path |
| Observability | Distributed tracing (OpenTelemetry) + per-tenant metrics | Pinpoints slow tenants or hot shards before they affect others |
