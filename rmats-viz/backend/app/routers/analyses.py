from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal, get_db
from app.models.analysis import Analysis, SampleGroup
from app.schemas.analysis import AnalysisListItem, AnalysisResponse, UploadResponse
from app.services.parser import parse_and_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])

_BATCH = 10_000


async def _do_delete(analysis_id: uuid.UUID) -> None:
    """Perform batched cascade deletion in a dedicated session.

    Runs as a background task so the HTTP 204 is returned to the browser
    immediately, avoiding connection timeouts on large analyses.
    """
    logger.info("DELETE /analyses/%s — background deletion starting", analysis_id)
    async with AsyncSessionLocal() as db:
        try:
            # deep_analysis_events — batched via ctid
            while True:
                r = await db.execute(text(
                    "DELETE FROM deep_analysis_events WHERE ctid IN ("
                    "  SELECT dae.ctid FROM deep_analysis_events dae"
                    "  JOIN deep_analyses da ON dae.deep_analysis_id = da.id"
                    "  WHERE da.analysis_id = :aid LIMIT :b"
                    ")"
                ), {"aid": analysis_id, "b": _BATCH})
                await db.commit()
                if r.rowcount == 0:
                    break

            await db.execute(text("DELETE FROM deep_analyses WHERE analysis_id = :aid"), {"aid": analysis_id})
            await db.commit()

            # event_splice_feature
            while True:
                r = await db.execute(text(
                    "DELETE FROM event_splice_feature WHERE event_id IN "
                    "(SELECT id FROM splicing_events WHERE analysis_id = :aid LIMIT :b)"
                ), {"aid": analysis_id, "b": _BATCH})
                await db.commit()
                if r.rowcount == 0:
                    break

            # event_cluster
            await db.execute(text("DELETE FROM event_cluster WHERE analysis_id = :aid"), {"aid": analysis_id})
            await db.commit()

            # splicing_events — batched
            while True:
                r = await db.execute(text(
                    "DELETE FROM splicing_events WHERE id IN "
                    "(SELECT id FROM splicing_events WHERE analysis_id = :aid LIMIT :b)"
                ), {"aid": analysis_id, "b": _BATCH})
                await db.commit()
                if r.rowcount == 0:
                    break

            # Parent row (sample_groups cascade via DB FK)
            await db.execute(delete(Analysis).where(Analysis.id == analysis_id))
            await db.commit()
            logger.info("DELETE /analyses/%s — done", analysis_id)

        except Exception:
            logger.exception("DELETE /analyses/%s — background deletion failed", analysis_id)


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    name: str = Form(...),
    group1_label: str = Form("Patients"),
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
    """Accept a delete request, verify existence, and return 204 immediately.

    The actual cascade deletion runs as a background task so large analyses
    (100k+ events) do not hold the HTTP connection open long enough to trigger
    browser or proxy timeouts.
    """
    result = await db.execute(select(Analysis.id).where(Analysis.id == analysis_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    logger.info("DELETE /analyses/%s — accepted, queuing background deletion", analysis_id)
    background_tasks.add_task(_do_delete, analysis_id)
