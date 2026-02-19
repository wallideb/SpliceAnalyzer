from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.schemas.event import EventsPage, SplicingEventResponse

router = APIRouter(tags=["events"])


@router.get("/analyses/{analysis_id}/events", response_model=EventsPage)
async def list_events(
    analysis_id: uuid.UUID,
    event_type: str | None = Query(None),
    gene_symbol: str | None = Query(None),
    fdr_max: float | None = Query(None, ge=0, le=1),
    sort_by: Literal["fdr", "abs_inc_level_diff", "gene_symbol"] = Query("fdr"),
    sort_dir: Literal["asc", "desc"] = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    # Verify analysis exists
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    q = select(SplicingEvent).where(SplicingEvent.analysis_id == analysis_id)

    if event_type:
        q = q.where(SplicingEvent.event_type == event_type.upper())
    if gene_symbol:
        q = q.where(SplicingEvent.gene_symbol.ilike(f"%{gene_symbol}%"))
    if fdr_max is not None:
        q = q.where(SplicingEvent.fdr <= fdr_max)

    # Count total
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Sort
    sort_col = getattr(SplicingEvent, sort_by)
    if sort_dir == "desc":
        sort_col = sort_col.desc().nulls_last()
    else:
        sort_col = sort_col.asc().nulls_last()

    q = q.order_by(sort_col).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    pages = max(1, -(-total // page_size))  # ceiling division
    return EventsPage(items=rows, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/analyses/{analysis_id}/events/top10", response_model=list[SplicingEventResponse])
async def get_top10(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    q = (
        select(SplicingEvent)
        .where(SplicingEvent.analysis_id == analysis_id)
        .where(SplicingEvent.top_rank.isnot(None))
        .order_by(SplicingEvent.top_rank)
    )
    rows = (await db.execute(q)).scalars().all()
    return rows
