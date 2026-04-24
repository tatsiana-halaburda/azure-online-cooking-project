# Azure Practice 2 & 3 — API-first (Option V)

Three local FastAPI apps talk to **one** Azure SQL database and use **separate schemas** (no cross-schema SQL joins for names; Ordering calls Inventory over HTTP):

- **Inventory** (`services/inventory`) → `[Tanya_Inventory]` — `Warehouses`, `Ingredients`, `Stock`
- **Ordering** (`services/ordering`) → `[Tanya_Ordering]` — `Orders`, `OrderItems`, `StockReservations`
- **Feedback** (`services/feedback`) → `[Tanya_Feedback]` — `FeedbackEntries`, `FeedbackSummary`

Ports: **8001** inventory, **8002** ordering, **8003** feedback.

**Practice 3:** After `POST /orders`, Ordering sends `order_created` JSON to an Azure Service Bus queue (send SAS). Inventory polls the queue on an interval (listen SAS) and exposes `GET /service-bus/recent-events`.

## Environment

Copy `.env.example` → `.env`. Connection strings: one line each; single quotes recommended (e.g. `'Endpoint=sb://…;SharedAccessKeyName=…;SharedAccessKey=…'`).

| Variable | Required | Used by |
|----------|----------|---------|
| `DB_SERVER`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD` | Yes (unless SQL string below) | All services with DB |
| `AZURE_SQL_CONNECTION_STRING` | No | Overrides `DB_*` when set |
| `DB_ODBC_DRIVER` | No | Default `ODBC Driver 18 for SQL Server` |
| `INVENTORY_SERVICE_URL` | No | Ordering → Inventory HTTP; default `http://localhost:8001`. Compose sets `http://inventory:8001` for ordering |
| `AZURE_SERVICEBUS_SEND_CONNECTION_STRING` | Optional | Ordering — send after `POST /orders` |
| `AZURE_SERVICEBUS_LISTEN_CONNECTION_STRING` | Optional | Inventory — background receive |
| `AZURE_SERVICEBUS_QUEUE_NAME` | Optional | Both — same queue; required with either SAS line above |
| `AZURE_SERVICEBUS_POLL_INTERVAL_SECONDS` | No | Inventory — seconds between receive attempts (default **5**) |

If Service Bus vars are omitted, orders still save; Inventory skips the listener. Failed sends are logged only.

## Azure SQL setup (once per database)

Run the scripts **in order** against the same DB as in `.env` (Azure Data Studio, SSMS, or `sqlcmd`):

1. `sql/01_schemas.sql`
2. `sql/02_inventory.sql`
3. `sql/03_ordering.sql`
4. `sql/04_feedback.sql`
5. `sql/05_seed.sql`

There is **no** `db-init` container in this repo — apply SQL manually (or wire your own init job).

**Practice 3 check:** `GET http://127.0.0.1:8001/health` → `service_bus_listener: true` when listen SAS + queue name are set; `POST http://127.0.0.1:8002/orders`; after ≥ poll interval, `GET http://127.0.0.1:8001/service-bus/recent-events`. Code: `libs/service_bus.py`, `libs/service_bus_listener.py`.

## API

Base: `http://127.0.0.1` — **8001** inventory, **8002** ordering, **8003** feedback.

**Check endpoints**

- `GET …/8001/health` · `8002` · `8003`

**Inventory (8001)**

- `GET /health` — includes `service_bus_listener` (Practice 3)
- `GET /service-bus/recent-events` — last queue payloads (in-memory, max 50)
- `GET /ingredients` — query: `category`, `name_contains`, `include_inactive`
- `POST /ingredients`
- `GET /ingredients/{ingredient_id}`
- `PUT /ingredients/{ingredient_id}`
- `DELETE /ingredients/{ingredient_id}` — soft delete (`IsActive = 0`)
- `GET /warehouses` — query: `include_inactive`
- `POST /warehouses`
- `GET /warehouses/{warehouse_id}`
- `PUT /warehouses/{warehouse_id}`
- `DELETE /warehouses/{warehouse_id}` — hard delete (**409** if stock still references it)
- `GET /stock` — query: `ingredient_id`, `warehouse_id`
- `POST /stock`
- `GET /stock/{stock_id}`
- `PUT /stock/{stock_id}`
- `DELETE /stock/{stock_id}`

**Ordering (8002)**

- `GET /health`
- `GET /orders` — query: `status`
- `POST /orders` — line items, `TotalCost`; enqueues `order_created` if send connection string + queue name set
- `GET /orders/{order_id}` — enriched with ingredient **names** via Inventory HTTP (**503** if Inventory fails)
- `PUT /orders/{order_id}`
- `DELETE /orders/{order_id}` — deletes reservations, items, then order
- `GET /orders/{order_id}/items`
- `POST /orders/{order_id}/items`
- `PUT /orders/{order_id}/items/{item_id}`
- `DELETE /orders/{order_id}/items/{item_id}` — recalculates order `TotalCost`
- `GET /orders/{order_id}/reservations`
- `POST /orders/{order_id}/reservations`
- `PUT /stock-reservations/{reservation_id}`
- `DELETE /stock-reservations/{reservation_id}`

**Feedback (8003)**

- `GET /health`
- `POST /feedback`
- `GET /feedback/entries/{feedback_id}`
- `PUT /feedback/entries/{feedback_id}` — refreshes summary for that ingredient
- `DELETE /feedback/entries/{feedback_id}` — refreshes summary
- `GET /feedback/ingredients/{ingredient_id}/summary` — from summary table or live aggregate
- `PUT /feedback/ingredients/{ingredient_id}/summary` — manual upsert of summary row
- `DELETE /feedback/ingredients/{ingredient_id}/summary`
- `GET /feedback/{ingredient_id}` — list entries; query: `include_archived`

**OpenAPI**

- `http://127.0.0.1:8001/docs` · `http://127.0.0.1:8002/docs` · `http://127.0.0.1:8003/docs`

## Docker run (recommended)

Docker Desktop on, repo root, `.env` with DB (and Service Bus if Practice 3):

```bash
docker compose up --build -d
```

Compose sets `INVENTORY_SERVICE_URL=http://inventory:8001` for ordering. Stop: `docker compose down`. Seed GUIDs: `sql/05_seed.sql`.

## Local run (without Docker)

Use a venv so `pyodbc` matches your Python (macOS: `brew install unixodbc`, Microsoft ODBC Driver 18, see `.env.example`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Three terminals from the **repo root**:

```bash
.venv/bin/uvicorn services.inventory.main:app --host 127.0.0.1 --port 8001
```

```bash
.venv/bin/uvicorn services.ordering.main:app --host 127.0.0.1 --port 8002
```

```bash
.venv/bin/uvicorn services.feedback.main:app --host 127.0.0.1 --port 8003
```

Start **inventory** first so ordering can resolve `INVENTORY_SERVICE_URL` (default `http://localhost:8001`).
