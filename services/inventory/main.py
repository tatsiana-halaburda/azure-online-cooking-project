import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import pyodbc
from fastapi import FastAPI, HTTPException, Query, status
from libs import service_bus as service_bus_config
from libs.db import cursor
from libs.service_bus_listener import poll_queue_forever, recent_events
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    stop = asyncio.Event()
    task: asyncio.Task[None] | None = None
    if service_bus_config.listen_connection_string() and service_bus_config.queue_name():
        task = asyncio.create_task(poll_queue_forever(stop))
    yield
    stop.set()
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Inventory Service", version="1.0.0", lifespan=_lifespan)


def _programming_schema_gone(exc: pyodbc.ProgrammingError) -> bool:
    msg = str(exc)
    return "42S02" in msg or "Invalid object name" in msg


# --- Ingredients ---


class Ingredient(BaseModel):
    ingredient_id: uuid.UUID
    name: str
    category: str
    unit: str
    reorder_level: float
    is_active: bool


class IngredientCreate(BaseModel):
    name: str
    category: str
    unit: str
    reorder_level: float = Field(ge=0)


class IngredientUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    unit: str | None = None
    reorder_level: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


def _row_to_ingredient(row: Any) -> Ingredient:
    return Ingredient(
        ingredient_id=uuid.UUID(str(row.IngredientId)),
        name=row.Name,
        category=row.Category,
        unit=row.Unit,
        reorder_level=float(row.ReorderLevel),
        is_active=bool(row.IsActive),
    )


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        sb_on = bool(service_bus_config.listen_connection_string() and service_bus_config.queue_name())
        return {"status": "ok", "service_bus_listener": sb_on}
    except Exception as exc:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.get("/service-bus/recent-events")
def service_bus_recent_events() -> dict[str, Any]:
    """Last messages received from the queue (in-memory; for local demos)."""
    return {"events": recent_events()}


@app.get("/ingredients", response_model=list[Ingredient])
def list_ingredients(
    category: str | None = None,
    name_contains: str | None = None,
    include_inactive: bool = Query(default=False),
) -> list[Ingredient]:
    try:
        with cursor() as cur:
            sql = """
                SELECT IngredientId, Name, Category, Unit, ReorderLevel, IsActive
                FROM [Tanya_Inventory].[Ingredients]
                WHERE 1 = 1
                """
            params: list[Any] = []
            if not include_inactive:
                sql += " AND IsActive = 1"
            if category:
                sql += " AND Category = ?"
                params.append(category)
            if name_contains:
                sql += " AND Name LIKE ?"
                params.append(f"%{name_contains}%")
            sql += " ORDER BY Name"
            cur.execute(sql, params)
            return [_row_to_ingredient(r) for r in cur.fetchall()]
    except pyodbc.ProgrammingError as exc:
        if _programming_schema_gone(exc):
            raise HTTPException(status_code=503, detail="No tables yet — run sql/01 … sql/05 on this DB, then retry.") from exc
        raise


@app.post("/ingredients", response_model=Ingredient, status_code=status.HTTP_201_CREATED)
def create_ingredient(body: IngredientCreate) -> Ingredient:
    iid = uuid.uuid4()
    try:
        with cursor() as cur:
            cur.execute(
                """
                INSERT INTO [Tanya_Inventory].[Ingredients]
                  (IngredientId, Name, Category, Unit, ReorderLevel, IsActive)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (str(iid), body.name, body.category, body.unit, body.reorder_level),
            )
    except pyodbc.ProgrammingError as exc:
        if _programming_schema_gone(exc):
            raise HTTPException(status_code=503, detail="No tables yet — run sql/01 … sql/05 on this DB, then retry.") from exc
        raise
    except pyodbc.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Ingredient name already exists") from exc
    return get_ingredient(iid)


@app.get("/ingredients/{id}", response_model=Ingredient)
def get_ingredient(id: uuid.UUID) -> Ingredient:
    try:
        with cursor() as cur:
            cur.execute(
                """
                SELECT IngredientId, Name, Category, Unit, ReorderLevel, IsActive
                FROM [Tanya_Inventory].[Ingredients]
                WHERE IngredientId = ?
                """,
                str(id),
            )
            row = cur.fetchone()
    except pyodbc.ProgrammingError as exc:
        if _programming_schema_gone(exc):
            raise HTTPException(status_code=503, detail="No tables yet — run sql/01 … sql/05 on this DB, then retry.") from exc
        raise

    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return _row_to_ingredient(row)


@app.put("/ingredients/{id}", response_model=Ingredient)
def update_ingredient(id: uuid.UUID, body: IngredientUpdate) -> Ingredient:
    get_ingredient(id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return get_ingredient(id)
    col_map = {
        "name": "Name",
        "category": "Category",
        "unit": "Unit",
        "reorder_level": "ReorderLevel",
        "is_active": "IsActive",
    }
    sets: list[str] = []
    params: list[Any] = []
    for key, val in fields.items():
        sets.append(f"{col_map[key]} = ?")
        params.append(int(val) if key == "is_active" else val)
    params.append(str(id))
    try:
        with cursor() as cur:
            cur.execute(
                f"UPDATE [Tanya_Inventory].[Ingredients] SET {', '.join(sets)} WHERE IngredientId = ?",
                params,
            )
    except pyodbc.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Ingredient name already exists") from exc
    return get_ingredient(id)


@app.delete("/ingredients/{id}", response_model=Ingredient)
def delete_ingredient(id: uuid.UUID) -> Ingredient:
    """Soft-delete (IsActive = 0)."""
    inv = get_ingredient(id)
    with cursor() as cur:
        cur.execute(
            "UPDATE [Tanya_Inventory].[Ingredients] SET IsActive = 0 WHERE IngredientId = ?",
            str(id),
        )
    return get_ingredient(id)


# --- Warehouses ---


class Warehouse(BaseModel):
    warehouse_id: uuid.UUID
    name: str
    location: str
    is_active: bool


class WarehouseCreate(BaseModel):
    name: str
    location: str


class WarehouseUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    is_active: bool | None = None


def _row_to_warehouse(row: Any) -> Warehouse:
    return Warehouse(
        warehouse_id=uuid.UUID(str(row.WarehouseId)),
        name=row.Name,
        location=row.Location,
        is_active=bool(row.IsActive),
    )


@app.get("/warehouses", response_model=list[Warehouse])
def list_warehouses(include_inactive: bool = Query(default=False)) -> list[Warehouse]:
    with cursor() as cur:
        if include_inactive:
            cur.execute(
                """
                SELECT WarehouseId, Name, Location, IsActive
                FROM [Tanya_Inventory].[Warehouses]
                ORDER BY Name
                """
            )
        else:
            cur.execute(
                """
                SELECT WarehouseId, Name, Location, IsActive
                FROM [Tanya_Inventory].[Warehouses]
                WHERE IsActive = 1
                ORDER BY Name
                """
            )
        return [_row_to_warehouse(r) for r in cur.fetchall()]


@app.post("/warehouses", response_model=Warehouse, status_code=status.HTTP_201_CREATED)
def create_warehouse(body: WarehouseCreate) -> Warehouse:
    wid = uuid.uuid4()
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO [Tanya_Inventory].[Warehouses] (WarehouseId, Name, Location, IsActive)
            VALUES (?, ?, ?, 1)
            """,
            (str(wid), body.name, body.location),
        )
    return get_warehouse(wid)


@app.get("/warehouses/{warehouse_id}", response_model=Warehouse)
def get_warehouse(warehouse_id: uuid.UUID) -> Warehouse:
    with cursor() as cur:
        cur.execute(
            """
            SELECT WarehouseId, Name, Location, IsActive
            FROM [Tanya_Inventory].[Warehouses]
            WHERE WarehouseId = ?
            """,
            str(warehouse_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return _row_to_warehouse(row)


@app.put("/warehouses/{warehouse_id}", response_model=Warehouse)
def update_warehouse(warehouse_id: uuid.UUID, body: WarehouseUpdate) -> Warehouse:
    get_warehouse(warehouse_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return get_warehouse(warehouse_id)
    col_map = {"name": "Name", "location": "Location", "is_active": "IsActive"}
    sets = []
    params: list[Any] = []
    for key, val in fields.items():
        sets.append(f"{col_map[key]} = ?")
        params.append(int(val) if key == "is_active" else val)
    params.append(str(warehouse_id))
    with cursor() as cur:
        cur.execute(
            f"UPDATE [Tanya_Inventory].[Warehouses] SET {', '.join(sets)} WHERE WarehouseId = ?",
            params,
        )
    return get_warehouse(warehouse_id)


@app.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(warehouse_id: uuid.UUID) -> None:
    get_warehouse(warehouse_id)
    try:
        with cursor() as cur:
            cur.execute("DELETE FROM [Tanya_Inventory].[Warehouses] WHERE WarehouseId = ?", str(warehouse_id))
    except pyodbc.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete warehouse while stock rows reference it (remove stock first or soft-disable only).",
        ) from exc


# --- Stock ---


class StockRow(BaseModel):
    stock_id: uuid.UUID
    ingredient_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float
    expiration_date: date | None


class StockCreate(BaseModel):
    ingredient_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: float = Field(ge=0)
    expiration_date: date | None = None


class StockUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    expiration_date: date | None = None


def _row_to_stock(row: Any) -> StockRow:
    exp = row.ExpirationDate
    return StockRow(
        stock_id=uuid.UUID(str(row.StockId)),
        ingredient_id=uuid.UUID(str(row.IngredientId)),
        warehouse_id=uuid.UUID(str(row.WarehouseId)),
        quantity=float(row.Quantity),
        expiration_date=exp if exp is not None else None,
    )


@app.get("/stock", response_model=list[StockRow])
def list_stock(
    ingredient_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> list[StockRow]:
    with cursor() as cur:
        sql = """
            SELECT StockId, IngredientId, WarehouseId, Quantity, ExpirationDate
            FROM [Tanya_Inventory].[Stock]
            WHERE 1 = 1
            """
        params: list[Any] = []
        if ingredient_id:
            sql += " AND IngredientId = ?"
            params.append(str(ingredient_id))
        if warehouse_id:
            sql += " AND WarehouseId = ?"
            params.append(str(warehouse_id))
        sql += " ORDER BY StockId"
        cur.execute(sql, params)
        return [_row_to_stock(r) for r in cur.fetchall()]


@app.post("/stock", response_model=StockRow, status_code=status.HTTP_201_CREATED)
def create_stock(body: StockCreate) -> StockRow:
    get_ingredient(body.ingredient_id)
    get_warehouse(body.warehouse_id)
    sid = uuid.uuid4()
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO [Tanya_Inventory].[Stock]
              (StockId, IngredientId, WarehouseId, Quantity, ExpirationDate)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(sid), str(body.ingredient_id), str(body.warehouse_id), body.quantity, body.expiration_date),
        )
    return get_stock(sid)


@app.get("/stock/{stock_id}", response_model=StockRow)
def get_stock(stock_id: uuid.UUID) -> StockRow:
    with cursor() as cur:
        cur.execute(
            """
            SELECT StockId, IngredientId, WarehouseId, Quantity, ExpirationDate
            FROM [Tanya_Inventory].[Stock]
            WHERE StockId = ?
            """,
            str(stock_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Stock row not found")
    return _row_to_stock(row)


@app.put("/stock/{stock_id}", response_model=StockRow)
def update_stock(stock_id: uuid.UUID, body: StockUpdate) -> StockRow:
    get_stock(stock_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return get_stock(stock_id)
    sets = []
    params: list[Any] = []
    if "quantity" in fields:
        sets.append("Quantity = ?")
        params.append(fields["quantity"])
    if "expiration_date" in fields:
        sets.append("ExpirationDate = ?")
        params.append(fields["expiration_date"])
    params.append(str(stock_id))
    with cursor() as cur:
        cur.execute(
            f"UPDATE [Tanya_Inventory].[Stock] SET {', '.join(sets)} WHERE StockId = ?",
            params,
        )
    return get_stock(stock_id)


@app.delete("/stock/{stock_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stock(stock_id: uuid.UUID) -> None:
    get_stock(stock_id)
    with cursor() as cur:
        cur.execute("DELETE FROM [Tanya_Inventory].[Stock] WHERE StockId = ?", str(stock_id))
