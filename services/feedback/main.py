import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import pyodbc
from fastapi import FastAPI, HTTPException, Query, status
from libs.db import cursor, transaction
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="Feedback Service", version="1.0.0")


class FeedbackEntryOut(BaseModel):
    feedback_id: uuid.UUID
    ingredient_id: uuid.UUID
    source: str
    rating: int
    comment: str | None
    is_archived: bool
    created_at: datetime


class FeedbackCreate(BaseModel):
    ingredient_id: uuid.UUID
    source: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class FeedbackUpdate(BaseModel):
    source: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    is_archived: bool | None = None


class FeedbackSummaryOut(BaseModel):
    ingredient_id: uuid.UUID
    avg_rating: float
    total_count: int
    last_updated: datetime


class FeedbackSummaryUpsert(BaseModel):
    avg_rating: float = Field(ge=1, le=5)
    total_count: int = Field(ge=0)


def _row_entry(row: Any) -> FeedbackEntryOut:
    return FeedbackEntryOut(
        feedback_id=uuid.UUID(str(row.FeedbackId)),
        ingredient_id=uuid.UUID(str(row.IngredientId)),
        source=row.Source,
        rating=int(row.Rating),
        comment=row.Comment,
        is_archived=bool(row.IsArchived),
        created_at=row.CreatedAt,
    )


def _refresh_summary_for_ingredient(cur: pyodbc.Cursor, ingredient_id: uuid.UUID) -> None:
    cur.execute(
        """
        SELECT
          AVG(CAST(Rating AS DECIMAL(4,2))) AS AvgR,
          COUNT(*) AS Cnt
        FROM [Tanya_Feedback].[FeedbackEntries]
        WHERE IngredientId = ? AND IsArchived = 0
        """,
        str(ingredient_id),
    )
    agg = cur.fetchone()
    cnt = int(agg.Cnt) if agg and agg.Cnt is not None else 0
    if cnt == 0:
        cur.execute(
            "DELETE FROM [Tanya_Feedback].[FeedbackSummary] WHERE IngredientId = ?",
            str(ingredient_id),
        )
        return
    avg_r = float(agg.AvgR) if agg.AvgR is not None else 0.0
    cur.execute(
        "SELECT SummaryId FROM [Tanya_Feedback].[FeedbackSummary] WHERE IngredientId = ?",
        str(ingredient_id),
    )
    existing = cur.fetchone()
    now = datetime.now(UTC)
    if existing:
        cur.execute(
            """
            UPDATE [Tanya_Feedback].[FeedbackSummary]
            SET AvgRating = ?, TotalCount = ?, LastUpdated = ?
            WHERE IngredientId = ?
            """,
            (avg_r, cnt, now, str(ingredient_id)),
        )
    else:
        sid = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO [Tanya_Feedback].[FeedbackSummary]
              (SummaryId, IngredientId, AvgRating, TotalCount, LastUpdated)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(sid), str(ingredient_id), avg_r, cnt, now),
        )


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


@app.post("/feedback", response_model=FeedbackEntryOut, status_code=status.HTTP_201_CREATED)
def create_feedback(body: FeedbackCreate) -> FeedbackEntryOut:
    fid = uuid.uuid4()
    now = datetime.now(UTC)
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO [Tanya_Feedback].[FeedbackEntries]
              (FeedbackId, IngredientId, Source, Rating, Comment, IsArchived, CreatedAt)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (str(fid), str(body.ingredient_id), body.source, body.rating, body.comment, now),
        )
        _refresh_summary_for_ingredient(cur, body.ingredient_id)
    return get_feedback_entry(fid)


def get_feedback_entry(feedback_id: uuid.UUID) -> FeedbackEntryOut:
    with cursor() as cur:
        cur.execute(
            """
            SELECT FeedbackId, IngredientId, Source, Rating, Comment, IsArchived, CreatedAt
            FROM [Tanya_Feedback].[FeedbackEntries]
            WHERE FeedbackId = ?
            """,
            str(feedback_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Feedback entry not found")
    return _row_entry(row)


@app.get("/feedback/entries/{feedback_id}", response_model=FeedbackEntryOut)
def get_feedback_entry_route(feedback_id: uuid.UUID) -> FeedbackEntryOut:
    return get_feedback_entry(feedback_id)


@app.put("/feedback/entries/{feedback_id}", response_model=FeedbackEntryOut)
def update_feedback_entry(feedback_id: uuid.UUID, body: FeedbackUpdate) -> FeedbackEntryOut:
    entry = get_feedback_entry(feedback_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return entry
    sets: list[str] = []
    params: list[Any] = []
    col_map = {"source": "Source", "rating": "Rating", "comment": "Comment", "is_archived": "IsArchived"}
    for key, val in fields.items():
        sets.append(f"{col_map[key]} = ?")
        params.append(int(val) if key == "is_archived" else val)
    params.append(str(feedback_id))
    with transaction() as cur:
        cur.execute(
            f"UPDATE [Tanya_Feedback].[FeedbackEntries] SET {', '.join(sets)} WHERE FeedbackId = ?",
            params,
        )
        _refresh_summary_for_ingredient(cur, entry.ingredient_id)
    return get_feedback_entry(feedback_id)


@app.delete("/feedback/entries/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback_entry(feedback_id: uuid.UUID) -> None:
    entry = get_feedback_entry(feedback_id)
    iid = entry.ingredient_id
    with transaction() as cur:
        cur.execute("DELETE FROM [Tanya_Feedback].[FeedbackEntries] WHERE FeedbackId = ?", str(feedback_id))
        _refresh_summary_for_ingredient(cur, iid)


@app.get("/feedback/ingredients/{ingredient_id}/summary", response_model=FeedbackSummaryOut)
def get_feedback_summary(ingredient_id: uuid.UUID) -> FeedbackSummaryOut:
    with cursor() as cur:
        cur.execute(
            """
            SELECT IngredientId, AvgRating, TotalCount, LastUpdated
            FROM [Tanya_Feedback].[FeedbackSummary]
            WHERE IngredientId = ?
            """,
            str(ingredient_id),
        )
        row = cur.fetchone()
    if row:
        return FeedbackSummaryOut(
            ingredient_id=uuid.UUID(str(row.IngredientId)),
            avg_rating=float(row.AvgRating),
            total_count=int(row.TotalCount),
            last_updated=row.LastUpdated,
        )
    with cursor() as cur:
        cur.execute(
            """
            SELECT
              AVG(CAST(Rating AS DECIMAL(4,2))) AS AvgR,
              COUNT(*) AS Cnt
            FROM [Tanya_Feedback].[FeedbackEntries]
            WHERE IngredientId = ? AND IsArchived = 0
            """,
            str(ingredient_id),
        )
        live = cur.fetchone()
    cnt = int(live.Cnt) if live and live.Cnt is not None else 0
    if cnt == 0:
        raise HTTPException(status_code=404, detail="No feedback for this ingredient")
    avg_r = float(live.AvgR) if live.AvgR is not None else 0.0
    return FeedbackSummaryOut(
        ingredient_id=ingredient_id,
        avg_rating=avg_r,
        total_count=cnt,
        last_updated=datetime.now(UTC),
    )


@app.put("/feedback/ingredients/{ingredient_id}/summary", response_model=FeedbackSummaryOut)
def put_feedback_summary(ingredient_id: uuid.UUID, body: FeedbackSummaryUpsert) -> FeedbackSummaryOut:
    now = datetime.now(UTC)
    with transaction() as cur:
        cur.execute(
            "SELECT SummaryId FROM [Tanya_Feedback].[FeedbackSummary] WHERE IngredientId = ?",
            str(ingredient_id),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE [Tanya_Feedback].[FeedbackSummary]
                SET AvgRating = ?, TotalCount = ?, LastUpdated = ?
                WHERE IngredientId = ?
                """,
                (body.avg_rating, body.total_count, now, str(ingredient_id)),
            )
        else:
            sid = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO [Tanya_Feedback].[FeedbackSummary]
                  (SummaryId, IngredientId, AvgRating, TotalCount, LastUpdated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(sid), str(ingredient_id), body.avg_rating, body.total_count, now),
            )
    return get_feedback_summary(ingredient_id)


@app.delete("/feedback/ingredients/{ingredient_id}/summary", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback_summary(ingredient_id: uuid.UUID) -> None:
    with cursor() as cur:
        cur.execute(
            "SELECT 1 FROM [Tanya_Feedback].[FeedbackSummary] WHERE IngredientId = ?",
            str(ingredient_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Summary not found")
        cur.execute(
            "DELETE FROM [Tanya_Feedback].[FeedbackSummary] WHERE IngredientId = ?",
            str(ingredient_id),
        )


@app.get("/feedback/{ingredient_id}", response_model=list[FeedbackEntryOut])
def list_feedback(
    ingredient_id: uuid.UUID,
    include_archived: bool = Query(default=False),
) -> list[FeedbackEntryOut]:
    with cursor() as cur:
        if include_archived:
            cur.execute(
                """
                SELECT FeedbackId, IngredientId, Source, Rating, Comment, IsArchived, CreatedAt
                FROM [Tanya_Feedback].[FeedbackEntries]
                WHERE IngredientId = ?
                ORDER BY CreatedAt DESC
                """,
                str(ingredient_id),
            )
        else:
            cur.execute(
                """
                SELECT FeedbackId, IngredientId, Source, Rating, Comment, IsArchived, CreatedAt
                FROM [Tanya_Feedback].[FeedbackEntries]
                WHERE IngredientId = ? AND IsArchived = 0
                ORDER BY CreatedAt DESC
                """,
                str(ingredient_id),
            )

        rows = cur.fetchall()

    return [_row_entry(r) for r in rows]
