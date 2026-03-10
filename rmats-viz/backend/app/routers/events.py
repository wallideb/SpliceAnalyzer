from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.schemas.event import EventsPage, ManhattanPoint, SplicingEventResponse

router = APIRouter(tags=["events"])


@router.get("/analyses/{analysis_id}/events", response_model=EventsPage)
async def list_events(
    analysis_id: uuid.UUID,
    event_type: str | None = Query(None),
    gene_symbol: str | None = Query(None),
    fdr_max: float | None = Query(None, ge=0, le=1),
    p_value_max: float | None = Query(None, ge=0, le=1),
    delta_psi_min: float | None = Query(None, ge=0, le=1),
    sort_by: Literal["fdr", "p_value", "abs_inc_level_diff", "gene_symbol"] = Query("fdr"),
    sort_dir: Literal["asc", "desc"] = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    exclude_top10: bool = Query(False, description="When true, hide top-10 ranked events"),
    db: AsyncSession = Depends(get_db),
):
    # Verify analysis exists
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    conditions = [SplicingEvent.analysis_id == analysis_id]

    if event_type:
        conditions.append(SplicingEvent.event_type == event_type.upper())
    if gene_symbol:
        conditions.append(SplicingEvent.gene_symbol.ilike(f"%{gene_symbol}%"))
    if fdr_max is not None:
        conditions.append(SplicingEvent.fdr <= fdr_max)
    if p_value_max is not None:
        conditions.append(SplicingEvent.p_value <= p_value_max)
    if delta_psi_min is not None:
        conditions.append(SplicingEvent.abs_inc_level_diff >= delta_psi_min)
    if exclude_top10:
        conditions.append(SplicingEvent.top_rank.is_(None))

    q = select(SplicingEvent).where(and_(*conditions))

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
async def get_top10(
    analysis_id: uuid.UUID,
    event_type: str | None = Query(None, description="Filter by event type (SE, RI, A3SS, A5SS, MXE)"),
    limit: int = Query(10, ge=1, le=50, description="Number of top events to return"),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    if event_type or limit != 10:
        # Dynamic top-N for a specific event type (or custom limit):
        # rank by FDR ASC, |ΔΨ| DESC
        conditions = [SplicingEvent.analysis_id == analysis_id]
        if event_type:
            conditions.append(SplicingEvent.event_type == event_type.upper())
        q = (
            select(SplicingEvent)
            .where(*conditions)
            .order_by(
                SplicingEvent.fdr.asc().nulls_last(),
                SplicingEvent.abs_inc_level_diff.desc().nulls_last(),
            )
            .limit(limit)
        )
    else:
        # Default: pre-computed global top-10
        q = (
            select(SplicingEvent)
            .where(SplicingEvent.analysis_id == analysis_id)
            .where(SplicingEvent.top_rank.isnot(None))
            .order_by(SplicingEvent.top_rank)
        )
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/analyses/{analysis_id}/events/manhattan", response_model=list[ManhattanPoint])
async def get_manhattan(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return lightweight event data for the Manhattan plot (all events, no pagination)."""
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    q = (
        select(
            SplicingEvent.id,
            SplicingEvent.event_type,
            SplicingEvent.gene_symbol,
            SplicingEvent.chr,
            SplicingEvent.exon_start,
            SplicingEvent.fdr,
            SplicingEvent.inc_level_difference,
        )
        .where(SplicingEvent.analysis_id == analysis_id)
        .where(SplicingEvent.chr.isnot(None))
        .where(SplicingEvent.exon_start.isnot(None))
        .order_by(SplicingEvent.chr, SplicingEvent.exon_start)
    )
    rows = (await db.execute(q)).all()
    return [
        ManhattanPoint(
            id=r.id,
            event_type=r.event_type,
            gene_symbol=r.gene_symbol,
            chr=r.chr,
            position=r.exon_start,
            fdr=r.fdr,
            inc_level_difference=r.inc_level_difference,
        )
        for r in rows
    ]
