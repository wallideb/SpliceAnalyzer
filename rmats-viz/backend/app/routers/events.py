from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.schemas.event import EventsPage, ManhattanPoint

router = APIRouter(tags=["events"])


# ---------------------------------------------------------------------------
# Natural chromosome ordering
# ---------------------------------------------------------------------------

# Canonical rank of the human chromosomes: 1..22, X=23, Y=24, M/MT=25.
_CHR_RANK: dict[str, int] = {str(i): i for i in range(1, 23)}
_CHR_RANK.update({"X": 23, "Y": 24, "M": 25, "MT": 25})
_CHR_OTHER_RANK = 100  # contigs / scaffolds sort after the canonical set, by name


def _chr_sort_key(chrom: str | None) -> tuple[int, str]:
    """Natural sort key for chromosome names.

    ``chr1`` … ``chr22`` → 1 … 22, ``chrX`` → 23, ``chrY`` → 24, ``chrM``/``chrMT``
    → 25; anything else (unplaced contigs, alt scaffolds, None) → 100 + name so
    they sort after the canonical chromosomes, alphabetically.  A leading
    ``chr`` prefix (any case) is ignored.
    """
    name = (chrom or "").strip()
    if name[:3].lower() == "chr":
        name = name[3:]
    rank = _CHR_RANK.get(name.upper())
    if rank is not None:
        return rank, ""
    return _CHR_OTHER_RANK, name.upper()


def _chr_order_sql():
    """SQL ordering expressions equivalent to :func:`_chr_sort_key`.

    Returns ``(rank_expr, name_expr)`` to be used as
    ``ORDER BY rank_expr, name_expr, exon_start``.  The rank is a CASE built
    from the same mapping (chr prefix stripped, case-insensitive).
    """
    stripped = func.upper(func.regexp_replace(SplicingEvent.chr, "^[cC][hH][rR]", ""))
    rank = case(
        {name: rank for name, rank in _CHR_RANK.items()},
        value=stripped,
        else_=_CHR_OTHER_RANK,
    )
    return rank, stripped


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

    Rows are returned in natural genomic order (chr1 … chr22, X, Y, M, then
    other contigs; by exon start within a chromosome).

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
    chr_rank, chr_name = _chr_order_sql()
    natural_order = (chr_rank, chr_name, SplicingEvent.exon_start)

    # Check total count first
    total = (await db.execute(
        select(func.count()).select_from(
            select(SplicingEvent.id).where(base_cond).subquery()
        )
    )).scalar_one()

    if total <= _MANHATTAN_MAX_POINTS:
        # Small enough — return everything
        q = select(*cols).where(base_cond).order_by(*natural_order)
        rows = (await db.execute(q)).all()
    else:
        from sqlalchemy import or_

        # Keep all significant events, sample the rest
        sig_q = (
            select(*cols)
            .where(and_(base_cond, SplicingEvent.fdr < 0.05))
            .order_by(*natural_order)
        )
        sig_rows = (await db.execute(sig_q)).all()

        remaining_budget = max(0, _MANHATTAN_MAX_POINTS - len(sig_rows))
        if remaining_budget > 0:
            nonsig_count = total - len(sig_rows)
            sample_rate = max(1, nonsig_count // remaining_budget)
            # Non-significant = FDR >= 0.05 OR FDR IS NULL.  Row numbers follow
            # the natural chromosome order so the every-Nth sampling spreads
            # the budget evenly along the genome.
            nonsig_cond = or_(SplicingEvent.fdr >= 0.05, SplicingEvent.fdr.is_(None))
            sub = (
                select(
                    *cols,
                    func.row_number().over(order_by=list(natural_order)).label("rn"),
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
                .where(sub.c.rn % sample_rate == 0)
                .order_by(sub.c.rn)
            )
            nonsig_rows = (await db.execute(sampled_q)).all()
        else:
            nonsig_rows = []

        rows = list(sig_rows) + list(nonsig_rows)

    # Final natural ordering in Python (≤ 50k rows) — authoritative regardless
    # of how the SQL side ordered / merged the two subsets.
    rows = sorted(rows, key=lambda r: (*_chr_sort_key(r.chr), r.exon_start or 0))

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
