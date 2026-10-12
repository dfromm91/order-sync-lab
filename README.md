# Order Sync Lab

A small Python/SQLite portfolio integration that moves synthetic sales orders to a mock ERP over HTTP. Demonstrates input mapping, exact money arithmetic, duplicate prevention, bounded retries, failed-record quarantine and reconciliation.

**This is an adjacent ERP integration exercise, not a NetSuite implementation.** No NetSuite SDK, account, SuiteScript execution or live ERP credentials are used. Created with Codex assistance; review the code and exercises before discussing it as portfolio work.

## Run (Python 3.11+; standard library only)

```sh
python3 -m unittest -v
python3 demo.py
```

The demo starts a loopback-only HTTP server on a random port, injects one 503 error, submits the same source order twice, sends a single remote record after retry, and reconciles totals. Expected: `sent`, 2 attempts, 5985 total cents and no reconciliation issues. No external requests or real data.

## Architecture

Source -> validate/map -> SQLite outbox -> REST adapter -> mock ERP -> reconciliation.

- `sync.py`: domain mapping, durable SQLite schema, sequential delivery worker and REST adapter.
- `demo.py`: mock HTTP API and end-to-end scenario.
- `test_sync.py`: money/quantity validation, duplicate conflict, HTTP retry, remote idempotency, permanent failures, exhausted retry budget, missing/mismatched records.
- `connect('orders.db')` uses a persistent database; the repeatable demo uses memory.

The external order ID is a stable identity. A changed payload with the same ID is rejected instead of silently overwriting an order. Decimal input is converted to integer cents. Transient HTTP errors retry with bounded exponential delays. Remote idempotency is essential: an ERP might accept an order before the response is lost. Reconciliation compares full mapped records, including totals.

## Limits and next steps

This is a sequential training worker, not a production service. No authentication, concurrent workers, pagination, server-side persistent idempotency, inventory reservations, updates/cancellations or reconciliation of unexpected remote records. A failed row is retained for inspection; manual replay is not implemented. The mock's in-memory records disappear on restart. Production integration needs OAuth, secret management, rate-limit/Retry-After handling, backoff jitter, durable remote idempotency, monitoring, schema contracts and accounting review. Never point it at a live financial system without implementing and validating these controls.

## Interview preparation (about 2 evenings)

1. Trace DEMO-001 from source fields to JSON and explain why 19.95 * 3 becomes 5985 cents.
2. Explain why local duplicate detection alone cannot prevent a remote duplicate after a timeout. Add a test simulating an accepted order followed by a lost response.
3. Add a second synthetic order and an invalid SKU. Explain the permanent-versus-transient error decision.
4. Change a remote total and show reconciliation identifying the mismatch.
5. Read Oracle NetSuite REST web services documentation. Sketch where authentication, record mapping, pagination and rate limits would change this adapter. Do not claim hands-on NetSuite experience from this lab.

A truthful portfolio bullet: “Implemented a Python/SQLite order-integration lab with a mock ERP REST API, idempotent delivery, bounded retries, exact monetary mapping, and reconciliation tests.”
