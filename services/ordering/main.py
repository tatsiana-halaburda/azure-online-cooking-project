import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
import pyodbc
from fastapi import FastAPI, HTTPException, Query, status
from libs.db import cursor, transaction
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8001").rstrip("/")
HTTP_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

app = FastAPI(title="Ordering Service", version="1.0.0")


def _load_order_sync(order_id: uuid.UUID) -> tuple[pyodbc.Row, list[pyodbc.Row], list[pyodbc.Row]]:
    with cursor() as cur:
        cur.execute(
            """
            SELECT OrderId, Status, CreatedAt, TotalCost, Notes
            FROM [Tanya_Ordering].[Orders]
            WHERE OrderId = ?
            """,
            str(order_id),
        )
        order_row = cur.fetchone()
        if not order_row:
            raise LookupError("order not found")

        cur.execute(
            """
            SELECT OrderItemId, OrderId, IngredientId, Quantity, UnitPrice
            FROM [Tanya_Ordering].[OrderItems]
            WHERE OrderId = ?
            ORDER BY OrderItemId
            """,
            str(order_id),
        )
        item_rows = cur.fetchall()

        cur.execute(
            """
            SELECT ReservationId, OrderId, IngredientId, ReservedQty, Status
            FROM [Tanya_Ordering].[StockReservations]
            WHERE OrderId = ?
            ORDER BY ReservationId
            """,
            str(order_id),
        )
        reservation_rows = cur.fetchall()

    return order_row, list(item_rows), list(reservation_rows)


class OrderItemOut(BaseModel):
    order_item_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: float
    unit_price: float
    ingredient_name: str


class StockReservationOut(BaseModel):
    reservation_id: uuid.UUID
    ingredient_id: uuid.UUID
    reserved_qty: float
    status: str
    ingredient_name: str


class OrderDetail(BaseModel):
    order_id: uuid.UUID
    status: str
    created_at: datetime
    total_cost: float
    notes: str | None = None
    items: list[OrderItemOut]
    reservations: list[StockReservationOut] = Field(default_factory=list)


class OrderSummary(BaseModel):
    order_id: uuid.UUID
    status: str
    created_at: datetime
    total_cost: float
    notes: str | None = None


class OrderItemCreate(BaseModel):
    ingredient_id: uuid.UUID
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class OrderCreate(BaseModel):
    status: str = "Draft"
    notes: str | None = None
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    total_cost: float | None = Field(default=None, ge=0)


class OrderItemRow(BaseModel):
    order_item_id: uuid.UUID
    order_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: float
    unit_price: float


class StockReservationRow(BaseModel):
    reservation_id: uuid.UUID
    order_id: uuid.UUID
    ingredient_id: uuid.UUID
    reserved_qty: float
    status: str


class StockReservationCreate(BaseModel):
    ingredient_id: uuid.UUID
    reserved_qty: float = Field(gt=0)
    status: str = "Active"


class StockReservationUpdate(BaseModel):
    reserved_qty: float | None = Field(default=None, gt=0)
    status: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


async def _fetch_ingredient_name(client: httpx.AsyncClient, ingredient_id: uuid.UUID) -> str:
    url = f"{INVENTORY_SERVICE_URL}/ingredients/{ingredient_id}"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Inventory service unavailable (timeout)") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Inventory service unavailable (connection error)") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail="Inventory service unavailable (non-success response)") from exc

    data = resp.json()
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=503, detail="Inventory service returned an unexpected payload")
    return name


@app.get("/orders", response_model=list[OrderSummary])
def list_orders(status_filter: str | None = Query(default=None, alias="status")) -> list[OrderSummary]:
    with cursor() as cur:
        if status_filter:
            cur.execute(
                """
                SELECT OrderId, Status, CreatedAt, TotalCost, Notes
                FROM [Tanya_Ordering].[Orders]
                WHERE Status = ?
                ORDER BY CreatedAt DESC
                """,
                status_filter,
            )
        else:
            cur.execute(
                """
                SELECT OrderId, Status, CreatedAt, TotalCost, Notes
                FROM [Tanya_Ordering].[Orders]
                ORDER BY CreatedAt DESC
                """
            )
        return [
            OrderSummary(
                order_id=uuid.UUID(str(r.OrderId)),
                status=r.Status,
                created_at=r.CreatedAt,
                total_cost=float(r.TotalCost),
                notes=r.Notes,
            )
            for r in cur.fetchall()
        ]


@app.post("/orders", response_model=OrderSummary, status_code=status.HTTP_201_CREATED)
def create_order(body: OrderCreate) -> OrderSummary:
    oid = uuid.uuid4()
    total = sum(it.quantity * it.unit_price for it in body.items)
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO [Tanya_Ordering].[Orders] (OrderId, Status, CreatedAt, TotalCost, Notes)
            VALUES (?, ?, SYSUTCDATETIME(), ?, ?)
            """,
            (str(oid), body.status, total, body.notes),
        )
        for it in body.items:
            iid = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO [Tanya_Ordering].[OrderItems]
                  (OrderItemId, OrderId, IngredientId, Quantity, UnitPrice)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(iid), str(oid), str(it.ingredient_id), it.quantity, it.unit_price),
            )
    return get_order_summary(oid)


def get_order_summary(order_id: uuid.UUID) -> OrderSummary:
    with cursor() as cur:
        cur.execute(
            """
            SELECT OrderId, Status, CreatedAt, TotalCost, Notes
            FROM [Tanya_Ordering].[Orders]
            WHERE OrderId = ?
            """,
            str(order_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderSummary(
        order_id=uuid.UUID(str(row.OrderId)),
        status=row.Status,
        created_at=row.CreatedAt,
        total_cost=float(row.TotalCost),
        notes=row.Notes,
    )


@app.get("/orders/{id}", response_model=OrderDetail)
async def get_order(id: uuid.UUID) -> OrderDetail:
    try:
        order_row, item_rows, reservation_rows = await asyncio.to_thread(_load_order_sync, id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Order not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    ingredient_ids: set[uuid.UUID] = set()
    for r in item_rows:
        ingredient_ids.add(uuid.UUID(str(r.IngredientId)))
    for r in reservation_rows:
        ingredient_ids.add(uuid.UUID(str(r.IngredientId)))

    names_by_id: dict[uuid.UUID, str] = {}
    sorted_ingredient_ids = sorted(ingredient_ids, key=lambda x: str(x))
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if sorted_ingredient_ids:
            try:
                fetched = await asyncio.gather(
                    *[_fetch_ingredient_name(client, iid) for iid in sorted_ingredient_ids]
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Inventory service unavailable") from exc

            for iid, name in zip(sorted_ingredient_ids, fetched, strict=True):
                names_by_id[iid] = name

    items_out: list[OrderItemOut] = []
    for r in item_rows:
        iid = uuid.UUID(str(r.IngredientId))
        items_out.append(
            OrderItemOut(
                order_item_id=uuid.UUID(str(r.OrderItemId)),
                ingredient_id=iid,
                quantity=float(r.Quantity),
                unit_price=float(r.UnitPrice),
                ingredient_name=names_by_id[iid],
            )
        )

    reservations_out: list[StockReservationOut] = []
    for r in reservation_rows:
        iid = uuid.UUID(str(r.IngredientId))
        reservations_out.append(
            StockReservationOut(
                reservation_id=uuid.UUID(str(r.ReservationId)),
                ingredient_id=iid,
                reserved_qty=float(r.ReservedQty),
                status=r.Status,
                ingredient_name=names_by_id[iid],
            )
        )

    return OrderDetail(
        order_id=uuid.UUID(str(order_row.OrderId)),
        status=order_row.Status,
        created_at=order_row.CreatedAt,
        total_cost=float(order_row.TotalCost),
        notes=order_row.Notes,
        items=items_out,
        reservations=reservations_out,
    )


@app.put("/orders/{id}", response_model=OrderSummary)
def update_order(id: uuid.UUID, body: OrderUpdate) -> OrderSummary:
    get_order_summary(id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return get_order_summary(id)
    sets: list[str] = []
    params: list[Any] = []
    if "status" in fields:
        sets.append("Status = ?")
        params.append(fields["status"])
    if "notes" in fields:
        sets.append("Notes = ?")
        params.append(fields["notes"])
    if "total_cost" in fields:
        sets.append("TotalCost = ?")
        params.append(fields["total_cost"])
    params.append(str(id))
    with cursor() as cur:
        cur.execute(
            f"UPDATE [Tanya_Ordering].[Orders] SET {', '.join(sets)} WHERE OrderId = ?",
            params,
        )
    return get_order_summary(id)


@app.delete("/orders/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(id: uuid.UUID) -> None:
    get_order_summary(id)
    with transaction() as cur:
        cur.execute("DELETE FROM [Tanya_Ordering].[StockReservations] WHERE OrderId = ?", str(id))
        cur.execute("DELETE FROM [Tanya_Ordering].[OrderItems] WHERE OrderId = ?", str(id))
        cur.execute("DELETE FROM [Tanya_Ordering].[Orders] WHERE OrderId = ?", str(id))


def _recalc_order_total(cur: pyodbc.Cursor, order_id: uuid.UUID) -> None:
    cur.execute(
        """
        SELECT ISNULL(SUM(CAST(Quantity AS DECIMAL(18,4)) * CAST(UnitPrice AS DECIMAL(18,4))), 0)
        FROM [Tanya_Ordering].[OrderItems]
        WHERE OrderId = ?
        """,
        str(order_id),
    )
    row = cur.fetchone()
    total = float(row[0]) if row else 0.0
    cur.execute(
        "UPDATE [Tanya_Ordering].[Orders] SET TotalCost = ? WHERE OrderId = ?",
        (total, str(order_id)),
    )


@app.get("/orders/{order_id}/items", response_model=list[OrderItemRow])
def list_order_items(order_id: uuid.UUID) -> list[OrderItemRow]:
    get_order_summary(order_id)
    with cursor() as cur:
        cur.execute(
            """
            SELECT OrderItemId, OrderId, IngredientId, Quantity, UnitPrice
            FROM [Tanya_Ordering].[OrderItems]
            WHERE OrderId = ?
            ORDER BY OrderItemId
            """,
            str(order_id),
        )
        return [
            OrderItemRow(
                order_item_id=uuid.UUID(str(r.OrderItemId)),
                order_id=uuid.UUID(str(r.OrderId)),
                ingredient_id=uuid.UUID(str(r.IngredientId)),
                quantity=float(r.Quantity),
                unit_price=float(r.UnitPrice),
            )
            for r in cur.fetchall()
        ]


@app.post("/orders/{order_id}/items", response_model=OrderItemRow, status_code=status.HTTP_201_CREATED)
def create_order_item(order_id: uuid.UUID, body: OrderItemCreate) -> OrderItemRow:
    get_order_summary(order_id)
    iid = uuid.uuid4()
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO [Tanya_Ordering].[OrderItems]
              (OrderItemId, OrderId, IngredientId, Quantity, UnitPrice)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(iid), str(order_id), str(body.ingredient_id), body.quantity, body.unit_price),
        )
        _recalc_order_total(cur, order_id)
    return get_order_item(order_id, iid)


def get_order_item(order_id: uuid.UUID, item_id: uuid.UUID) -> OrderItemRow:
    with cursor() as cur:
        cur.execute(
            """
            SELECT OrderItemId, OrderId, IngredientId, Quantity, UnitPrice
            FROM [Tanya_Ordering].[OrderItems]
            WHERE OrderItemId = ? AND OrderId = ?
            """,
            (str(item_id), str(order_id)),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order item not found")
    return OrderItemRow(
        order_item_id=uuid.UUID(str(row.OrderItemId)),
        order_id=uuid.UUID(str(row.OrderId)),
        ingredient_id=uuid.UUID(str(row.IngredientId)),
        quantity=float(row.Quantity),
        unit_price=float(row.UnitPrice),
    )


class OrderItemUpdate(BaseModel):
    ingredient_id: uuid.UUID | None = None
    quantity: float | None = Field(default=None, gt=0)
    unit_price: float | None = Field(default=None, ge=0)


@app.put("/orders/{order_id}/items/{item_id}", response_model=OrderItemRow)
def update_order_item(order_id: uuid.UUID, item_id: uuid.UUID, body: OrderItemUpdate) -> OrderItemRow:
    get_order_item(order_id, item_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return get_order_item(order_id, item_id)
    col_map = {"ingredient_id": "IngredientId", "quantity": "Quantity", "unit_price": "UnitPrice"}
    sets: list[str] = []
    params: list[Any] = []
    for key, val in fields.items():
        sets.append(f"{col_map[key]} = ?")
        params.append(str(val) if key == "ingredient_id" else val)
    params.extend([str(item_id), str(order_id)])
    with transaction() as cur:
        cur.execute(
            f"UPDATE [Tanya_Ordering].[OrderItems] SET {', '.join(sets)} WHERE OrderItemId = ? AND OrderId = ?",
            params,
        )
        _recalc_order_total(cur, order_id)
    return get_order_item(order_id, item_id)


@app.delete("/orders/{order_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order_item(order_id: uuid.UUID, item_id: uuid.UUID) -> None:
    get_order_item(order_id, item_id)
    with transaction() as cur:
        cur.execute(
            "DELETE FROM [Tanya_Ordering].[OrderItems] WHERE OrderItemId = ? AND OrderId = ?",
            (str(item_id), str(order_id)),
        )
        _recalc_order_total(cur, order_id)


@app.get("/orders/{order_id}/reservations", response_model=list[StockReservationRow])
def list_reservations(order_id: uuid.UUID) -> list[StockReservationRow]:
    get_order_summary(order_id)
    with cursor() as cur:
        cur.execute(
            """
            SELECT ReservationId, OrderId, IngredientId, ReservedQty, Status
            FROM [Tanya_Ordering].[StockReservations]
            WHERE OrderId = ?
            ORDER BY ReservationId
            """,
            str(order_id),
        )
        return [
            StockReservationRow(
                reservation_id=uuid.UUID(str(r.ReservationId)),
                order_id=uuid.UUID(str(r.OrderId)),
                ingredient_id=uuid.UUID(str(r.IngredientId)),
                reserved_qty=float(r.ReservedQty),
                status=r.Status,
            )
            for r in cur.fetchall()
        ]


@app.post("/orders/{order_id}/reservations", response_model=StockReservationRow, status_code=status.HTTP_201_CREATED)
def create_reservation(order_id: uuid.UUID, body: StockReservationCreate) -> StockReservationRow:
    get_order_summary(order_id)
    rid = uuid.uuid4()
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO [Tanya_Ordering].[StockReservations]
              (ReservationId, OrderId, IngredientId, ReservedQty, Status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(rid), str(order_id), str(body.ingredient_id), body.reserved_qty, body.status),
        )
    return get_reservation(rid)


def get_reservation(reservation_id: uuid.UUID) -> StockReservationRow:
    with cursor() as cur:
        cur.execute(
            """
            SELECT ReservationId, OrderId, IngredientId, ReservedQty, Status
            FROM [Tanya_Ordering].[StockReservations]
            WHERE ReservationId = ?
            """,
            str(reservation_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return StockReservationRow(
        reservation_id=uuid.UUID(str(row.ReservationId)),
        order_id=uuid.UUID(str(row.OrderId)),
        ingredient_id=uuid.UUID(str(row.IngredientId)),
        reserved_qty=float(row.ReservedQty),
        status=row.Status,
    )


@app.put("/stock-reservations/{reservation_id}", response_model=StockReservationRow)
def update_reservation(reservation_id: uuid.UUID, body: StockReservationUpdate) -> StockReservationRow:
    get_reservation(reservation_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return get_reservation(reservation_id)
    sets: list[str] = []
    params: list[Any] = []
    if "reserved_qty" in fields:
        sets.append("ReservedQty = ?")
        params.append(fields["reserved_qty"])
    if "status" in fields:
        sets.append("Status = ?")
        params.append(fields["status"])
    params.append(str(reservation_id))
    with cursor() as cur:
        cur.execute(
            f"UPDATE [Tanya_Ordering].[StockReservations] SET {', '.join(sets)} WHERE ReservationId = ?",
            params,
        )
    return get_reservation(reservation_id)


@app.delete("/stock-reservations/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservation(reservation_id: uuid.UUID) -> None:
    get_reservation(reservation_id)
    with cursor() as cur:
        cur.execute(
            "DELETE FROM [Tanya_Ordering].[StockReservations] WHERE ReservationId = ?",
            str(reservation_id),
        )
