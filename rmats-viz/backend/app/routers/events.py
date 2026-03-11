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


_MANHATTAN_MAX_POINTS = 50_000  # cap for browser performance


@router.get("/analyses/{analysis_id}/events/manhattan", response_model=list[ManhattanPoint])
async def get_manhattan(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return lightweight event data for the Manhattan plot.

    For large analyses (>50k events) we keep ALL significant events (FDR < 0.05)
    and uniformly sample the rest to stay under *_MANHATTAN_MAX_POINTS*.
    """
    res = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    base_cond = and_(
        SplicingEvent.analysis_id == analysis_id,
        SplicingEvent.chr.isnot(None),
        SplicingEvent.exon_start.isnot(None),
    )
    cols = (
        SplicingEvent.id,
        SplicingEvent.event_type,
        SplicingEvent.gene_symbol,
        SplicingEvent.chr,
        SplicingEvent.exon_start,
        SplicingEvent.fdr,
        SplicingEvent.inc_level_difference,
    )

    # Check total count first
    total = (await db.execute(
        select(func.count()).select_from(
            select(SplicingEvent.id).where(base_cond).subquery()
        )
    )).scalar_one()

    if total <= _MANHATTAN_MAX_POINTS:
        # Small enough — return everything
        q = select(*cols).where(base_cond).order_by(SplicingEvent.chr, SplicingEvent.exon_start)
        rows = (await db.execute(q)).all()
    else:
        from sqlalchemy import literal_column, or_

        # Keep all significant events, sample the rest
        sig_q = (
            select(*cols)
            .where(and_(base_cond, SplicingEvent.fdr < 0.05))
            .order_by(SplicingEvent.chr, SplicingEvent.exon_start)
        )
        sig_rows = (await db.execute(sig_q)).all()

        remaining_budget = max(0, _MANHATTAN_MAX_POINTS - len(sig_rows))
        if remaining_budget > 0:
            nonsig_count = total - len(sig_rows)
            sample_rate = max(1, nonsig_count // remaining_budget)
            # Non-significant = FDR >= 0.05 OR FDR IS NULL
            nonsig_cond = or_(SplicingEvent.fdr >= 0.05, SplicingEvent.fdr.is_(None))
            sub = (
                select(
                    *cols,
                    func.row_number().over(
                        order_by=[SplicingEvent.chr, SplicingEvent.exon_start]
                    ).label("rn"),
                )
                .where(and_(base_cond, nonsig_cond))
                .subquery()
            )
            sampled_q = (
                select(
                    sub.c.id, sub.c.event_type, sub.c.gene_symbol,
                    sub.c.chr, sub.c.exon_start, sub.c.fdr,
                    sub.c.inc_level_difference,
                )
                .where(literal_column("rn") % sample_rate == 0)
                .order_by(sub.c.chr, sub.c.exon_start)
            )
            nonsig_rows = (await db.execute(sampled_q)).all()
        else:
            nonsig_rows = []

        rows = sorted(
            list(sig_rows) + list(nonsig_rows),
            key=lambda r: (r.chr or "", r.exon_start or 0),
        )

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
