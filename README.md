# Order Sync Lab

A Python and SQLite integration project that synchronizes synthetic sales orders with a mock ERP through a REST API. It demonstrates practical approaches to reliable data delivery: validation, monetary precision, duplicate prevention, bounded retries, and reconciliation.

**Stack:** Python 3.11+ · SQLite · HTTP/JSON · `unittest`  
**Dependencies:** Python standard library only

## What it demonstrates

- **Data mapping and validation:** Convert source orders into an ERP-facing schema and reject malformed quantities, identifiers, and prices.
- **Financial precision:** Parse decimal prices and store monetary values as integer cents.
- **Duplicate prevention:** Use stable external order IDs in the outbox and an idempotency key at the mock API. Conflicting payloads are rejected rather than silently overwritten.
- **Failure handling:** Retry transient HTTP/network failures within a fixed attempt budget, using exponential delays. Retain failed records for inspection.
- **Reconciliation:** Compare successfully delivered records with remote data to identify missing or changed orders.
- **Automated verification:** Eight tests cover validation, duplicate conflicts, HTTP retries, remote idempotency, permanent failures, exhausted retry budgets, and reconciliation.

## Quick start

```sh
git clone https://github.com/dfromm91/order-sync-lab.git
cd order-sync-lab
python3 -m unittest -v
python3 demo.py
```

The demo starts a local HTTP server on a dynamically assigned port, injects a temporary HTTP 503 failure, and enqueues the same source order twice. The delivery worker retries successfully, creates one remote record, and verifies that it matches the source.

Expected result:

```json
{
  "outbox": [["DEMO-001", "sent", 2]],
  "erp_orders": [{
    "customer_ref": "SYNTHETIC-CUSTOMER",
    "external_id": "DEMO-001",
    "item_ref": "SENSOR-A",
    "quantity": 3,
    "total_cents": 5985,
    "unit_price_cents": 1995
  }],
  "reconciliation": []
}
```

All demo data is synthetic. The server listens on loopback, and the demo makes no external API requests.

## Architecture

```text
Source order
    -> Validate and map
    -> SQLite outbox
    -> REST delivery worker
    -> Mock ERP
    -> Reconciliation report
```

| File | Responsibility |
| --- | --- |
| `sync.py` | Validation, mapping, SQLite outbox, HTTP client, delivery worker, and reconciliation |
| `demo.py` | Local mock ERP API and executable end-to-end scenario |
| `test_sync.py` | Automated tests for data correctness and delivery behavior |

The outbox records payloads, delivery state, attempt counts, and errors. `connect('orders.db')` provides file-backed persistence; the repeatable demo and tests use an in-memory database.

## Design decisions

**Stable identity across delivery attempts.** An order's external ID identifies it throughout the pipeline. Re-enqueuing an identical order is a no-op; reusing the ID with different data raises a conflict. The REST client sends a deterministic idempotency key to address duplicate delivery at the receiving system.

**Exact money arithmetic.** Prices enter as decimal strings and become integer cents. Values with fractional cents are rejected, avoiding silent rounding.

**Explicit failure states.** Transient errors receive bounded retries; permanent errors and exhausted retries leave failed records available for inspection. A successful HTTP response marks a record as sent, while reconciliation separately checks the resulting remote data.

**A small, inspectable implementation.** Standard-library components keep setup lightweight and make the integration behavior easy to trace from source record to HTTP request and database state.

## Scope and future development

This project models an ERP integration using a mock API. It does not connect to NetSuite or any other live ERP platform.

The worker is sequential, and the mock API stores records and idempotency state in memory. Authentication, concurrent delivery, manual replay, pagination, inventory reservations, order updates/cancellations, and detection of unexpected remote records are outside the current scope.

Potential extensions include PostgreSQL-backed storage, OAuth2 authentication, durable remote idempotency, webhook ingestion, Retry-After handling, backoff jitter, and operational monitoring.

## Development

Created with Codex assistance. The repository contains the runnable implementation, automated tests, and a local demonstration so its behavior can be inspected and reproduced.
