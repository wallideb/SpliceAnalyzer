from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
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
    p_value_max: float | None = Query(None, ge=0, le=1),
    delta_psi_min: float | None = Query(None, ge=0, le=1),
    sort_by: Literal["fdr", "p_value", "abs_inc_level_diff", "gene_symbol"] = Query("fdr"),
    sort_dir: Literal["asc", "desc"] = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    # Verify analysis exists
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Build individual filter clauses
    type_clause = (SplicingEvent.event_type == event_type.upper()) if event_type else None
    gene_clause = SplicingEvent.gene_symbol.ilike(f"%{gene_symbol}%") if gene_symbol else None
    fdr_clause = (SplicingEvent.fdr <= fdr_max) if fdr_max is not None else None
    pval_clause = (SplicingEvent.p_value <= p_value_max) if p_value_max is not None else None
    dpsi_clause = (SplicingEvent.abs_inc_level_diff >= delta_psi_min) if delta_psi_min is not None else None

    stat_filters_active = fdr_clause is not None or pval_clause is not None or dpsi_clause is not None

    if stat_filters_active:
        # Events that satisfy all filters (including stat thresholds)
        full_conditions = [SplicingEvent.analysis_id == analysis_id]
        if type_clause is not None:
            full_conditions.append(type_clause)
        if gene_clause is not None:
            full_conditions.append(gene_clause)
        if fdr_clause is not None:
            full_conditions.append(fdr_clause)
        if pval_clause is not None:
            full_conditions.append(pval_clause)
        if dpsi_clause is not None:
            full_conditions.append(dpsi_clause)

        # Top-10 events always included regardless of stat thresholds
        top10_conditions = [
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.top_rank.isnot(None),
        ]
        if type_clause is not None:
            top10_conditions.append(type_clause)
        if gene_clause is not None:
            top10_conditions.append(gene_clause)

        q = select(SplicingEvent).where(
            or_(and_(*full_conditions), and_(*top10_conditions))
        )
    else:
        base_conditions = [SplicingEvent.analysis_id == analysis_id]
        if type_clause is not None:
            base_conditions.append(type_clause)
        if gene_clause is not None:
            base_conditions.append(gene_clause)
        q = select(SplicingEvent).where(and_(*base_conditions))

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
