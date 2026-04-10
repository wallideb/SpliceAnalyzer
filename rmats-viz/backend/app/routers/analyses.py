from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal, get_db
from app.models.analysis import Analysis, SampleGroup
from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent
from app.models.event import SplicingEvent
from app.models.splice import EventSpliceFeature
from app.schemas.analysis import AnalysisListItem, AnalysisResponse, UploadResponse
from app.services.parser import parse_and_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])


async def _do_delete(analysis_id: uuid.UUID) -> None:
    """Delete an analysis by explicitly removing each child table in dependency order.

    We do NOT rely on PostgreSQL's implicit CASCADE chain (triggered by a single
    DELETE on the parent row) because that mechanism scans FK-target columns
    row-by-row — any missing index on those columns causes O(n×m) full-table
    scans that hang for minutes on large datasets.

    Instead every statement here deletes by analysis_id (always indexed) or by
    a single subquery that resolves to analysis_id in one hop.  Each step is
    logged so the exact point of failure is immediately visible.

    On any failure (including asyncio.CancelledError from a container restart)
    the status is reset to 'error' so the user can retry.
    """
    logger.info("DELETE /analyses/%s — background deletion starting", analysis_id)
    try:
        async with AsyncSessionLocal() as db:
            # 1. Delete deep_analysis_events (FK → deep_analyses AND splicing_events).
            #    Resolved via deep_analyses.analysis_id (one-hop subquery).
            da_subq = select(DeepAnalysis.id).where(DeepAnalysis.analysis_id == analysis_id)
            r = await db.execute(
                delete(DeepAnalysisEvent).where(DeepAnalysisEvent.deep_analysis_id.in_(da_subq))
            )
            logger.info("DELETE /analyses/%s — deleted %d deep_analysis_events", analysis_id, r.rowcount)

            # 2. Delete event_splice_feature (FK → splicing_events).
            #    Resolved via splicing_events.analysis_id (one-hop subquery).
            ev_subq = select(SplicingEvent.id).where(SplicingEvent.analysis_id == analysis_id)
            r = await db.execute(
                delete(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(ev_subq))
            )
            logger.info("DELETE /analyses/%s — deleted %d event_splice_features", analysis_id, r.rowcount)

            # 3. Delete deep_analyses (direct analysis_id FK; deep_analysis_events already gone).
            r = await db.execute(
                delete(DeepAnalysis).where(DeepAnalysis.analysis_id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted %d deep_analyses", analysis_id, r.rowcount)

            # 4. Delete splicing_events (direct analysis_id FK; all dependents already gone).
            r = await db.execute(
                delete(SplicingEvent).where(SplicingEvent.analysis_id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted %d splicing_events", analysis_id, r.rowcount)

            # 5. Delete sample_groups (direct analysis_id FK).
            r = await db.execute(
                delete(SampleGroup).where(SampleGroup.analysis_id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted %d sample_groups", analysis_id, r.rowcount)

            # 6. Delete the analysis itself (all dependents gone; CASCADE finds nothing).
            r = await db.execute(
                delete(Analysis).where(Analysis.id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted analysis row (found=%d)", analysis_id, r.rowcount)

            await db.commit()
        logger.info("DELETE /analyses/%s — done", analysis_id)
    except BaseException:
        logger.exception("DELETE /analyses/%s — background deletion failed", analysis_id)
        # Reset status so the user can retry (don't leave it stuck as 'deleting').
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Analysis)
                    .where(Analysis.id == analysis_id)
                    .values(status="error", error_message="Deletion failed — please retry")
                )
                await db.commit()
        except Exception:
            logger.exception("DELETE /analyses/%s — failed to reset status after error", analysis_id)
        raise


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    name: str = Form(...),
    group1_label: str = Form("Subjects"),
    group2_label: str = Form("Controls"),
    group1_samples: str = Form("[]"),
    group2_samples: str = Form("[]"),
    mutated_genes: str = Form("[]"),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    analysis_id = uuid.uuid4()
    try:
        parsed_genes = json.loads(mutated_genes)
        if not isinstance(parsed_genes, list):
            parsed_genes = []
    except json.JSONDecodeError:
        parsed_genes = []
    analysis = Analysis(id=analysis_id, name=name, status="processing", mutated_genes=parsed_genes)
    db.add(analysis)

    try:
        g1_samples = json.loads(group1_samples)
        g2_samples = json.loads(group2_samples)
    except json.JSONDecodeError:
        g1_samples, g2_samples = [], []

    db.add(SampleGroup(analysis_id=analysis_id, group_label=group1_label, group_index=1, sample_names=g1_samples))
    db.add(SampleGroup(analysis_id=analysis_id, group_label=group2_label, group_index=2, sample_names=g2_samples))
    await db.flush()

    try:
        file_data = [(f.filename or f"file_{i}", await f.read()) for i, f in enumerate(files)]
        event_count = await parse_and_store(file_data, analysis_id, db)
        analysis.status = "ready"
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to parse analysis %s", analysis_id)
        async with AsyncSessionLocal() as err_db:
            err_analysis = await err_db.get(Analysis, analysis_id)
            if err_analysis:
                err_analysis.status = "error"
                err_analysis.error_message = str(exc)
            else:
                err_db.add(Analysis(id=analysis_id, name=name, status="error", error_message=str(exc)))
            await err_db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return UploadResponse(analysis_id=analysis_id, status="ready", event_count=event_count)


@router.get("", response_model=list[AnalysisListItem])
async def list_analyses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Analysis).order_by(Analysis.created_at.desc()))
    return result.scalars().all()


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.sample_groups))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Verify existence, mark the analysis as 'deleting', return 204 immediately.

    The actual deletion runs as a background task (single CASCADE DELETE) so
    the browser never waits on the heavy work.  Marking status='deleting'
    prevents a second concurrent delete request from queuing a duplicate task.
    """
    result = await db.execute(select(Analysis.id, Analysis.status).where(Analysis.id == analysis_id))
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if row.status == "deleting":
        # Already in progress — return 204 without queuing a second task.
        return

    await db.execute(
        update(Analysis).where(Analysis.id == analysis_id).values(status="deleting")
    )
    await db.commit()

    logger.info("DELETE /analyses/%s — accepted, queuing background deletion", analysis_id)
    background_tasks.add_task(_do_delete, analysis_id)
