# Azure Practice 2 & 3 — API-first (Option V)

Three local FastAPI apps talk to **one** Azure SQL database and use **separate schemas** (no cross-schema SQL joins for names; Ordering calls Inventory over HTTP):

- **Inventory** (`services/inventory`) → `[Tanya_Inventory]` — `Warehouses`, `Ingredients`, `Stock`
- **Ordering** (`services/ordering`) → `[Tanya_Ordering]` — `Orders`, `OrderItems`, `StockReservations`
- **Feedback** (`services/feedback`) → `[Tanya_Feedback]` — `FeedbackEntries`, `FeedbackSummary`

Ports: **8001** inventory, **8002** ordering, **8003** feedback.

**Practice 3:** Ordering sends an **`order_created`** JSON message to an **Azure Service Bus queue** after each successful `POST /orders`. Inventory runs a **background poller** (configurable interval) that receives messages with a separate SAS connection string. See [Practice 3: Azure Service Bus queue](#practice-3-azure-service-bus-queue).

## Environment

Copy `.env.example` to `.env` and fill in values:

```env
DB_USERNAME=name
DB_PASSWORD=password
DB_SERVER=tcp:yourserver.database.windows.net
DB_DATABASE=yourdb

INVENTORY_SERVICE_URL=http://localhost:8001
```

Optional: `AZURE_SQL_CONNECTION_STRING` (if set, it overrides `DB_*`). Optional: `DB_ODBC_DRIVER`.

For Practice 3, also set `AZURE_SERVICEBUS_SEND_CONNECTION_STRING`, `AZURE_SERVICEBUS_LISTEN_CONNECTION_STRING`, and `AZURE_SERVICEBUS_QUEUE_NAME` (see section below).

## Azure SQL setup (once per database)

Run the scripts **in order** against the same DB as in `.env` (Azure Data Studio, SSMS, or `sqlcmd`):

1. `sql/01_schemas.sql`
2. `sql/02_inventory.sql`
3. `sql/03_ordering.sql`
4. `sql/04_feedback.sql`
5. `sql/05_seed.sql`

There is **no** `db-init` container in this repo — apply SQL manually (or wire your own init job).

## Practice 3: Azure Service Bus queue

**Goal:** two services communicate through a shared queue—**send** on a business trigger, **receive** on a timer—using **different connection strings** (write vs read SAS) for least privilege.

| Piece | Service | Trigger / mode |
|--------|---------|----------------|
| **Send** | Ordering (`services/ordering`) | After a successful **`POST /orders`** (message includes `event`, `order_id`, `status`, `total_cost`, `notes`, `item_count`). |
| **Receive** | Inventory (`services/inventory`) | Background loop every **`AZURE_SERVICEBUS_POLL_INTERVAL_SECONDS`** (default **5**). Messages are completed after handling; the last **50** payloads are kept in memory for demos. |

**Environment variables** (see `.env.example`):

- `AZURE_SERVICEBUS_SEND_CONNECTION_STRING` — SAS policy with **Send** (used only by Ordering).
- `AZURE_SERVICEBUS_LISTEN_CONNECTION_STRING` — SAS policy with **Listen** (used only by Inventory).
- `AZURE_SERVICEBUS_QUEUE_NAME` — queue name (must match the queue both apps use).
- `AZURE_SERVICEBUS_POLL_INTERVAL_SECONDS` — optional; seconds between receive attempts in Inventory.

Use **one line per connection string** in `.env`; single quotes around the value are recommended (see `.env.example` comments).

**Verify locally**

1. Start Inventory, then Ordering (or `docker compose up --build -d` with `.env` present).
2. `GET http://127.0.0.1:8001/health` — includes `"service_bus_listener": true` when listen connection string and queue name are set for Inventory.
3. `POST http://127.0.0.1:8002/orders` with a valid body (seed ingredient IDs in `sql/05_seed.sql`).
4. Wait at least one poll interval, then `GET http://127.0.0.1:8001/service-bus/recent-events` — expect `order_created` entries.

If send or listen env vars are missing, Ordering still persists orders; Inventory skips starting the listener. Send failures are logged and do not roll back the SQL transaction.

**Code:** `libs/service_bus.py` (send), `libs/service_bus_listener.py` (async receive loop). Dependency: `azure-servicebus` in `requirements.txt`.

## API

Base: `http://127.0.0.1` — **8001** inventory, **8002** ordering, **8003** feedback.

**Check endpoints**

- `GET http://127.0.0.1:8001/health` — Inventory health includes `service_bus_listener` when Practice 3 env is set
- `GET http://127.0.0.1:8002/health`
- `GET http://127.0.0.1:8003/health`

**Inventory (8001)**

- `GET /health`
- `GET /service-bus/recent-events` — last messages read from the Service Bus queue (in-memory; Practice 3)
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
- `POST /orders` — body includes line items; sets `TotalCost` from lines; enqueues **`order_created`** to Service Bus when send env is configured (Practice 3)
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

1. Start **Docker Desktop**.

2. Build images:

```bash
docker compose build
```

3. After SQL scripts are applied on Azure SQL, start all APIs (rebuild if dependencies changed, e.g. after adding Service Bus):

```bash
docker compose up --build -d
```

Compose sets `INVENTORY_SERVICE_URL=http://inventory:8001` for **ordering** so it can reach inventory inside the network.

4. Try the routes in **[API](#api)** (seed GUIDs are in `sql/05_seed.sql`).

5. Stop:

```bash
docker compose down
```

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
