# Azure Practice 2 — API-first (Option V)

Three local FastAPI apps talk to **one** Azure SQL database and use **separate schemas** (no cross-schema SQL joins for names; Ordering calls Inventory over HTTP):

- **Inventory** (`services/inventory`) → `[Tanya_Inventory]` — `Warehouses`, `Ingredients`, `Stock`
- **Ordering** (`services/ordering`) → `[Tanya_Ordering]` — `Orders`, `OrderItems`, `StockReservations`
- **Feedback** (`services/feedback`) → `[Tanya_Feedback]` — `FeedbackEntries`, `FeedbackSummary`

Ports: **8001** inventory, **8002** ordering, **8003** feedback.

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

## Azure SQL setup (once per database)

Run the scripts **in order** against the same DB as in `.env` (Azure Data Studio, SSMS, or `sqlcmd`):

1. `sql/01_schemas.sql`
2. `sql/02_inventory.sql`
3. `sql/03_ordering.sql`
4. `sql/04_feedback.sql`
5. `sql/05_seed.sql`

There is **no** `db-init` container in this repo — apply SQL manually (or wire your own init job).

## API

Base: `http://127.0.0.1` — **8001** inventory, **8002** ordering, **8003** feedback.

**Check endpoints**

- `GET http://127.0.0.1:8001/health`
- `GET http://127.0.0.1:8002/health`
- `GET http://127.0.0.1:8003/health`

**Inventory (8001)**

- `GET /health`
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
- `POST /orders` — body includes line items; sets `TotalCost` from lines
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

3. After SQL scripts are applied on Azure SQL, start all APIs:

```bash
docker compose up -d
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
