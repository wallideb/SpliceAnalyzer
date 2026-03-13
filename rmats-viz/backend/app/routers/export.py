from __future__ import annotations

import asyncio
import logging
import uuid
from io import BytesIO
from typing import Literal

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.models.splice import EventSpliceFeature
from app.services.panelapp import get_panels_for_gene
from app.services.gene_ontology import get_go_terms
from app.services.stringdb import get_interaction

# ── Column group identifiers ──────────────────────────────────────────────────
ColumnGroup = Literal["core", "panelapp", "go", "stringdb"]
ALL_GROUPS: tuple[ColumnGroup, ...] = ("core", "panelapp", "go", "stringdb")

router = APIRouter(prefix="/export", tags=["export"])

# Limit concurrent outbound HTTP requests to external APIs (PanelApp, GO, STRING-DB)
# to avoid socket/connection-pool exhaustion on large exports (200+ genes).
_EXT_API_SEMAPHORE = asyncio.Semaphore(10)


async def _throttled(coro):
    """Run a coroutine under the external-API semaphore."""
    async with _EXT_API_SEMAPHORE:
        return await coro

# ── Colour constants ──────────────────────────────────────────────────────────
HEADER_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
HEADER_FONT = Font(bold=True)
ROW_FILL_ALT = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")


def _auto_size_columns(ws, min_width: int = 10, max_width: int = 40) -> None:
    """Resize each column to fit its content, clamped between min/max."""
    for col_cells in ws.columns:
        length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in col_cells
        )
        col_letter = get_column_letter(col_cells[0].column)
        ws.column_dimensions[col_letter].width = min(max(length + 2, min_width), max_width)


def _style_header_row(ws) -> None:
    """Apply bold + blue-fill to the first row."""
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _apply_row_banding(ws) -> None:
    """Apply alternating grey fill to even data rows (row 3, 5, …)."""
    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        if row_idx % 2 == 0:
            for cell in row:
                cell.fill = ROW_FILL_ALT


async def _get_analysis_with_groups(
    db: AsyncSession, analysis_id: uuid.UUID
) -> tuple["Analysis", str, str]:
    """Load an Analysis with its sample groups, returning group labels.

    Raises HTTPException(404) if not found.
    """
    q = await db.execute(
        select(Analysis)
        .options(joinedload(Analysis.sample_groups))
        .where(Analysis.id == analysis_id)
    )
    analysis = q.unique().scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    g1 = next((g for g in analysis.sample_groups if g.group_index == 1), None)
    g2 = next((g for g in analysis.sample_groups if g.group_index == 2), None)
    return analysis, g1.group_label if g1 else "Group 1", g2.group_label if g2 else "Group 2"


async def _load_events_and_features(
    db: AsyncSession, analysis_id: uuid.UUID
) -> tuple[list["SplicingEvent"], dict[uuid.UUID, "EventSpliceFeature"]]:
    """Fetch all events for an analysis and SE splice features keyed by event_id."""
    result = await db.execute(
        select(SplicingEvent).where(SplicingEvent.analysis_id == analysis_id)
    )
    events: list[SplicingEvent] = list(result.scalars().all())

    # Use subquery instead of materializing UUIDs (avoids parameter limit with large datasets)
    se_subq = select(SplicingEvent.id).where(
        SplicingEvent.analysis_id == analysis_id,
        SplicingEvent.event_type == "SE",
    )
    features: dict[uuid.UUID, EventSpliceFeature] = {}
    feat_result = await db.execute(
        select(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(se_subq))
    )
    for feat in feat_result.scalars().all():
        features[feat.event_id] = feat

    return events, features


@router.get("/{analysis_id}/excel")
async def export_analysis_excel(
    analysis_id: uuid.UUID,
    include: str = Query(
        "core",
        description=(
            "Comma-separated list of column groups to include. "
            "Allowed values: core, panelapp, go, stringdb. "
            "Example: ?include=core,panelapp,go"
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all splicing events for *analysis_id* as an Excel .xlsx file.

    Column groups
    -------------
    core      – gene, coordinates, rMATS statistics, splice features, MANE (always included)
    panelapp  – top PanelApp disease panel confidence and panel names per gene
    go        – top GO terms (BP / MF / CC) per gene via mygene.info
    stringdb  – highest STRING-DB combined score vs each analysis candidate gene
    """

    # ── Parse include groups ──────────────────────────────────────────────────
    requested: set[str] = {g.strip().lower() for g in include.split(",")}
    valid: set[str] = set(ALL_GROUPS)
    unknown = requested - valid
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown column group(s): {', '.join(sorted(unknown))}. "
                   f"Allowed: {', '.join(ALL_GROUPS)}",
        )
    # core is always included
    groups: set[str] = requested | {"core"}

    # ── 1. Verify analysis exists (with sample groups for labels) ────────────
    analysis, group1_label, group2_label = await _get_analysis_with_groups(db, analysis_id)

    # ── 2-3. Fetch all events + SE splice features ────────────────────────────
    events, features = await _load_events_and_features(db, analysis_id)

    # ── 4. Fetch external annotations (per unique gene symbol) ───────────────
    unique_symbols: list[str] = list({
        e.gene_symbol for e in events if e.gene_symbol
    })

    # PanelApp columns
    panelapp_data: dict[str, dict] = {}
    if "panelapp" in groups and unique_symbols:
        pa_results = await asyncio.gather(
            *[_throttled(get_panels_for_gene(sym)) for sym in unique_symbols],
            return_exceptions=True,
        )
        for sym, res in zip(unique_symbols, pa_results):
            if isinstance(res, list) and res:
                # Pick top confidence level: green > amber > red
                conf_order = {"green": 0, "amber": 1, "red": 2}
                top = min(res, key=lambda p: conf_order.get(p.get("confidence_label", ""), 3))
                panel_names = ", ".join(p.get("panel_name", "") for p in res[:3])
                panelapp_data[sym] = {
                    "confidence": top.get("confidence_label", ""),
                    "panels": panel_names,
                }
            else:
                panelapp_data[sym] = {"confidence": "", "panels": ""}

    # GO columns
    go_data: dict[str, dict] = {}
    if "go" in groups and unique_symbols:
        go_results = await asyncio.gather(
            *[_throttled(get_go_terms(sym, None)) for sym in unique_symbols],
            return_exceptions=True,
        )
        for sym, res in zip(unique_symbols, go_results):
            if isinstance(res, list):
                by_cat: dict[str, list[str]] = {"BP": [], "MF": [], "CC": []}
                for term in res:
                    cat = term.get("category", "")
                    if cat in by_cat:
                        by_cat[cat].append(term.get("term", ""))
                go_data[sym] = {
                    "BP": "; ".join(by_cat["BP"][:3]),
                    "MF": "; ".join(by_cat["MF"][:3]),
                    "CC": "; ".join(by_cat["CC"][:3]),
                }
            else:
                go_data[sym] = {"BP": "", "MF": "", "CC": ""}

    # STRING-DB columns — highest combined score vs any analysis mutated gene
    stringdb_data: dict[str, float | None] = {}
    if "stringdb" in groups and unique_symbols:
        mutated_genes: list[str] = [
            g.get("symbol", "") for g in (analysis.mutated_genes or [])
            if g.get("symbol")
        ]
        if mutated_genes:
            # Build all (event_gene, mutated_gene) pairs, skip self-pairs
            pairs = [
                (sym, mut)
                for sym in unique_symbols
                for mut in mutated_genes
                if sym.upper() != mut.upper()
            ]
            if pairs:
                interaction_results = await asyncio.gather(
                    *[_throttled(get_interaction(sym, mut)) for sym, mut in pairs],
                    return_exceptions=True,
                )
                # For each event gene, keep the highest combined_score across mutated genes
                for (sym, _mut), res in zip(pairs, interaction_results):
                    if isinstance(res, dict) and res.get("has_interaction"):
                        score = res.get("combined_score", 0.0) or 0.0
                        current = stringdb_data.get(sym)
                        if current is None or score > current:
                            stringdb_data[sym] = score
                    elif sym not in stringdb_data:
                        stringdb_data[sym] = None

    # ── 5. Build the workbook ─────────────────────────────────────────────────
    wb = openpyxl.Workbook()

    # ── Sheet 1 : Events ─────────────────────────────────────────────────────
    ws_events = wb.active
    ws_events.title = "Events"

    headers = [
        "Gene", "Gene ID", "Type", "Chromosome", "Strand",
        "Exon Start", "Exon End", "Exon Size",
        "p-value", "FDR", "ΔΨ", "|ΔΨ|",
        f"PSI {group1_label}", f"PSI {group2_label}",
        # SE splice features
        "Donor Site", "Canonical GT",
        "Acceptor Site", "Canonical AG",
        "PPT Score", "Max Y Run",
        "BP Found", "BP Distance",
        # Frame / MANE annotations
        "Frame", "Region", "CDS Length",
        "MANE Transcript", "Exon Rank",
    ]
    if "panelapp" in groups:
        headers += ["PanelApp Confidence", "PanelApp Panels"]
    if "go" in groups:
        headers += ["GO:BP", "GO:MF", "GO:CC"]
    if "stringdb" in groups:
        headers += ["STRING Max Score"]

    ws_events.append(headers)

    for event in events:
        feat = features.get(event.id) if event.event_type == "SE" else None
        sym = event.gene_symbol or ""

        row = [
            event.gene_symbol,
            event.gene_id,
            event.event_type,
            event.chr,
            event.strand,
            event.exon_start,
            event.exon_end,
            feat.exon_size if feat else None,
            event.p_value,
            event.fdr,
            event.inc_level_difference,
            event.abs_inc_level_diff,
            event.inc_level_1,
            event.inc_level_2,
            # Splice features (SE only)
            feat.donor_seq if feat else None,
            feat.donor_is_gt if feat else None,
            feat.acceptor_seq if feat else None,
            feat.acceptor_is_ag if feat else None,
            feat.ppt_score if feat else None,
            feat.ppt_longest_run if feat else None,
            feat.bp_motif_found if feat else None,
            feat.bp_distance if feat else None,
            # Frame / MANE
            feat.frame_class if feat else None,
            feat.frame_region if feat else None,
            feat.cds_exon_length if feat else None,
            feat.mane_transcript_id if feat else None,
            feat.exon_rank if feat else None,
        ]
        if "panelapp" in groups:
            pa = panelapp_data.get(sym, {"confidence": "", "panels": ""})
            row += [pa["confidence"], pa["panels"]]
        if "go" in groups:
            go = go_data.get(sym, {"BP": "", "MF": "", "CC": ""})
            row += [go["BP"], go["MF"], go["CC"]]
        if "stringdb" in groups:
            score = stringdb_data.get(sym)
            row += [round(score, 3) if score is not None else None]

        ws_events.append(row)

    _style_header_row(ws_events)
    _apply_row_banding(ws_events)
    _auto_size_columns(ws_events)
    ws_events.freeze_panes = "A2"
    ws_events.auto_filter.ref = ws_events.dimensions

    # ── Sheet 2 : Summary ────────────────────────────────────────────────────
    ws_summary = wb.create_sheet("Summary")
    ws_summary.append(["Column groups included", ", ".join(sorted(groups))])
    ws_summary.append([])

    # Count events by type
    type_counts: dict[str, int] = {}
    for event in events:
        type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1

    ws_summary.append(["Type", "Event Count"])
    for etype in ["SE", "RI", "A3SS", "A5SS", "MXE"]:
        ws_summary.append([etype, type_counts.get(etype, 0)])
    ws_summary.append(["Total", len(events)])

    # SE-specific statistics
    ws_summary.append([])  # blank separator
    ws_summary.append(["SE Statistics", ""])

    n_se = type_counts.get("SE", 0)
    if n_se > 0 and features:
        n_gt = sum(1 for f in features.values() if f.donor_is_gt is True)
        n_ag = sum(1 for f in features.values() if f.acceptor_is_ag is True)
        n_inframe = sum(
            1 for f in features.values() if f.frame_class == "in_frame"
        )
        n_frameshift = sum(
            1 for f in features.values() if f.frame_class == "frameshift"
        )
        n_feat = len(features)
        ws_summary.append(["SE events with annotated features", n_feat])
        ws_summary.append(["% canonical GT", f"{n_gt / n_feat * 100:.1f}%" if n_feat else "N/A"])
        ws_summary.append(["% canonical AG", f"{n_ag / n_feat * 100:.1f}%" if n_feat else "N/A"])
        ws_summary.append(["% in-frame", f"{n_inframe / n_feat * 100:.1f}%" if n_feat else "N/A"])
        ws_summary.append(["% frameshift", f"{n_frameshift / n_feat * 100:.1f}%" if n_feat else "N/A"])
    else:
        ws_summary.append(["No annotated SE features", ""])

    _style_header_row(ws_summary)
    _apply_row_banding(ws_summary)
    _auto_size_columns(ws_summary)

    # ── 5. Stream the response ────────────────────────────────────────────────
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_{analysis_id}.xlsx"'
        },
    )

@router.get("/{analysis_id}/deep-analysis/{deep_analysis_id}/excel")
async def export_deep_analysis_excel(
    analysis_id: uuid.UUID,
    deep_analysis_id: uuid.UUID,
    include: str = Query("core", description="Comma-separated column groups: core, panelapp, go, stringdb"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export only significant events from a deep analysis as Excel.

    Identical format to the full analysis export but scoped to
    events that passed the deep analysis thresholds.
    """
    from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent

    # Validate
    requested: set[str] = {g.strip().lower() for g in include.split(",")}
    unknown = requested - set(ALL_GROUPS)
    if unknown:
        raise HTTPException(422, f"Unknown column group(s): {', '.join(sorted(unknown))}")
    groups: set[str] = requested | {"core"}

    analysis, group1_label, group2_label = await _get_analysis_with_groups(db, analysis_id)

    deep = (await db.execute(
        select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
    )).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")

    # Fetch only significant events
    sig_q = (
        select(SplicingEvent)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            DeepAnalysisEvent.is_significant == True,
        )
        .order_by(SplicingEvent.fdr.asc().nulls_last())
    )
    events = list((await db.execute(sig_q)).scalars().all())

    # Load features for SE events (subquery avoids parameter limit)
    se_subq = (
        select(SplicingEvent.id)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            DeepAnalysisEvent.is_significant == True,
            SplicingEvent.event_type == "SE",
        )
    )
    features: dict[uuid.UUID, EventSpliceFeature] = {}
    feat_result = await db.execute(
        select(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(se_subq))
    )
    for feat in feat_result.scalars().all():
        features[feat.event_id] = feat

    # External annotations
    unique_symbols = list({e.gene_symbol for e in events if e.gene_symbol})
    panelapp_data: dict[str, dict] = {}
    go_data: dict[str, dict] = {}
    stringdb_data: dict[str, float | None] = {}

    if "panelapp" in groups and unique_symbols:
        pa_results = await asyncio.gather(
            *[_throttled(get_panels_for_gene(sym)) for sym in unique_symbols],
            return_exceptions=True,
        )
        for sym, res in zip(unique_symbols, pa_results):
            if isinstance(res, list) and res:
                conf_order = {"green": 0, "amber": 1, "red": 2}
                top = min(res, key=lambda p: conf_order.get(p.get("confidence_label", ""), 3))
                panelapp_data[sym] = {
                    "confidence": top.get("confidence_label", ""),
                    "panels": ", ".join(p.get("panel_name", "") for p in res[:3]),
                }
            else:
                panelapp_data[sym] = {"confidence": "", "panels": ""}

    if "go" in groups and unique_symbols:
        go_results = await asyncio.gather(
            *[_throttled(get_go_terms(sym, None)) for sym in unique_symbols],
            return_exceptions=True,
        )
        for sym, res in zip(unique_symbols, go_results):
            if isinstance(res, list):
                by_cat: dict[str, list[str]] = {"BP": [], "MF": [], "CC": []}
                for term in res:
                    cat = term.get("category", "")
                    if cat in by_cat:
                        by_cat[cat].append(term.get("term", ""))
                go_data[sym] = {
                    "BP": "; ".join(by_cat["BP"][:3]),
                    "MF": "; ".join(by_cat["MF"][:3]),
                    "CC": "; ".join(by_cat["CC"][:3]),
                }
            else:
                go_data[sym] = {"BP": "", "MF": "", "CC": ""}

    if "stringdb" in groups and unique_symbols:
        mutated_genes_list: list[str] = [
            g.get("symbol", "") for g in (analysis.mutated_genes or []) if g.get("symbol")
        ]
        if mutated_genes_list:
            pairs = [
                (sym, mut) for sym in unique_symbols for mut in mutated_genes_list
                if sym.upper() != mut.upper()
            ]
            if pairs:
                interaction_results = await asyncio.gather(
                    *[_throttled(get_interaction(sym, mut)) for sym, mut in pairs],
                    return_exceptions=True,
                )
                for (sym, _), res in zip(pairs, interaction_results):
                    if isinstance(res, dict) and res.get("has_interaction"):
                        score = res.get("combined_score", 0.0) or 0.0
                        current = stringdb_data.get(sym)
                        if current is None or score > current:
                            stringdb_data[sym] = score
                    elif sym not in stringdb_data:
                        stringdb_data[sym] = None

    # Build workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Significant Events"

    headers = [
        "Gene", "Gene ID", "Type", "Chromosome", "Strand",
        "Exon Start", "Exon End", "Exon Size",
        "p-value", "FDR", "ΔΨ", "|ΔΨ|",
        f"PSI {group1_label}", f"PSI {group2_label}",
        "Donor Site", "Canonical GT", "Acceptor Site", "Canonical AG",
        "PPT Score", "Max Y Run", "BP Found", "BP Distance",
        "Frame", "Region", "CDS Length", "MANE Transcript", "Exon Rank",
    ]
    if "panelapp" in groups:
        headers += ["PanelApp Confidence", "PanelApp Panels"]
    if "go" in groups:
        headers += ["GO:BP", "GO:MF", "GO:CC"]
    if "stringdb" in groups:
        headers += ["STRING Max Score"]

    ws.append(headers)
    for event in events:
        feat = features.get(event.id) if event.event_type == "SE" else None
        sym = event.gene_symbol or ""
        row = [
            event.gene_symbol, event.gene_id, event.event_type,
            event.chr, event.strand, event.exon_start, event.exon_end,
            feat.exon_size if feat else None,
            event.p_value, event.fdr, event.inc_level_difference, event.abs_inc_level_diff,
            event.inc_level_1, event.inc_level_2,
            feat.donor_seq if feat else None, feat.donor_is_gt if feat else None,
            feat.acceptor_seq if feat else None, feat.acceptor_is_ag if feat else None,
            feat.ppt_score if feat else None, feat.ppt_longest_run if feat else None,
            feat.bp_motif_found if feat else None, feat.bp_distance if feat else None,
            feat.frame_class if feat else None, feat.frame_region if feat else None,
            feat.cds_exon_length if feat else None, feat.mane_transcript_id if feat else None,
            feat.exon_rank if feat else None,
        ]
        if "panelapp" in groups:
            pa = panelapp_data.get(sym, {"confidence": "", "panels": ""})
            row += [pa["confidence"], pa["panels"]]
        if "go" in groups:
            go = go_data.get(sym, {"BP": "", "MF": "", "CC": ""})
            row += [go["BP"], go["MF"], go["CC"]]
        if "stringdb" in groups:
            score = stringdb_data.get(sym)
            row += [round(score, 3) if score is not None else None]
        ws.append(row)

    _style_header_row(ws)
    _apply_row_banding(ws)
    _auto_size_columns(ws)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Summary sheet
    ws_sum = wb.create_sheet("Summary")
    ws_sum.append(["Deep Analysis", deep.name or str(deep_analysis_id)])
    ws_sum.append(["FDR threshold", deep.fdr_threshold])
    ws_sum.append(["|ΔΨ| minimum", deep.delta_psi_min])
    ws_sum.append(["Significant events", len(events)])
    ws_sum.append([])
    type_counts: dict[str, int] = {}
    for ev in events:
        type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1
    ws_sum.append(["Type", "Count"])
    for et in ["SE", "RI", "A3SS", "A5SS", "MXE"]:
        ws_sum.append([et, type_counts.get(et, 0)])
    _style_header_row(ws_sum)
    _auto_size_columns(ws_sum)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    # Sanitise filename to ASCII (Starlette encodes headers as latin-1)
    name = (deep.name or "deep_analysis").replace(" ", "_")[:30]
    safe_name = name.encode("ascii", "ignore").decode("ascii") or "deep_analysis"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="rmats_{safe_name}_significant.xlsx"'},
    )


# ===========================================================================
# 3C — PDF Rapport d'analyse
# ===========================================================================

import math as _math
import statistics as _statistics
from collections import Counter
from datetime import date as _date

from reportlab.lib import colors as _colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4 as _A4
from reportlab.lib.styles import getSampleStyleSheet as _getStyles, ParagraphStyle
from reportlab.lib.units import cm as _cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group
from reportlab.graphics.charts.barcharts import VerticalBarChart
_W, _ = _A4
_MARGIN = 2 * _cm


def _build_styles() -> dict:
    base = _getStyles()
    styles = {
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"],
            fontSize=18, spaceAfter=8, textColor=_colors.HexColor("#1e3a5f"),
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"],
            fontSize=13, spaceBefore=12, spaceAfter=6,
            textColor=_colors.HexColor("#2563eb"),
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"],
            fontSize=10, spaceBefore=8, spaceAfter=4,
            textColor=_colors.HexColor("#475569"),
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontSize=9, leading=13, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"],
            fontSize=7.5, leading=11, textColor=_colors.HexColor("#64748b"),
        ),
        "code": ParagraphStyle(
            "Code", parent=base["Code"],
            fontSize=8, leading=11, textColor=_colors.HexColor("#0f172a"),
        ),
    }
    return styles


def _tbl_style(header_bg: str = "#1e3a5f") -> TableStyle:
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), _colors.HexColor(header_bg)),
        ("TEXTCOLOR",   (0, 0), (-1, 0), _colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_colors.white, _colors.HexColor("#f1f5f9")]),
        ("FONTSIZE",    (0, 1), (-1, -1), 7.5),
        ("GRID",        (0, 0), (-1, -1), 0.4, _colors.HexColor("#e2e8f0")),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])


# ---------------------------------------------------------------------------
# Figure builders (reportlab Drawings — resolution-independent vector)
# ---------------------------------------------------------------------------

def _fig_exon_size_histogram(exon_sizes: list[int]) -> Drawing | None:
    """Exon-size distribution histogram (25 nt bins)."""
    if not exon_sizes:
        return None

    BIN = 25
    max_size = max(exon_sizes)
    n_bins = min((_math.ceil(max_size / BIN) + 1), 40)  # cap bins
    counts = [0] * n_bins
    for s in exon_sizes:
        idx = min(s // BIN, n_bins - 1)
        counts[idx] = counts[idx] + 1

    # Drawing dimensions
    W, H = 440, 160
    MARGIN_L, MARGIN_B, MARGIN_T, MARGIN_R = 40, 30, 20, 20
    chart_w = W - MARGIN_L - MARGIN_R
    chart_h = H - MARGIN_B - MARGIN_T

    d = Drawing(W, H)

    # Background
    d.add(Rect(0, 0, W, H, fillColor=_colors.HexColor("#fafafa"),
               strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.5))

    max_count = max(counts) or 1
    bar_w = max(2, chart_w / n_bins - 1)

    # Bars
    for i, cnt in enumerate(counts):
        bar_h = (cnt / max_count) * chart_h
        x = MARGIN_L + i * (bar_w + 1)
        y = MARGIN_B
        d.add(Rect(x, y, bar_w, bar_h,
                    fillColor=_colors.HexColor("#3b82f6"),
                    strokeColor=None, fillOpacity=0.75))

    # X-axis labels (every 4 bins)
    for i in range(0, n_bins, 4):
        x = MARGIN_L + i * (bar_w + 1) + bar_w / 2
        d.add(String(x, MARGIN_B - 12, str(i * BIN),
                      fontSize=6, fontName="Helvetica", fillColor=_colors.HexColor("#475569"),
                      textAnchor="middle"))

    # X-axis title
    d.add(String(W / 2, 4, "Exon size (nt)",
                  fontSize=7, fontName="Helvetica-Oblique", fillColor=_colors.HexColor("#475569"),
                  textAnchor="middle"))

    # Y-axis labels (0, max/2, max)
    for val in [0, max_count // 2, max_count]:
        y = MARGIN_B + (val / max_count) * chart_h
        d.add(String(MARGIN_L - 4, y - 2, str(val),
                      fontSize=6, fontName="Helvetica", fillColor=_colors.HexColor("#475569"),
                      textAnchor="end"))
        d.add(Line(MARGIN_L, y, MARGIN_L + chart_w, y,
                    strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.3))

    # Y-axis title (rotated via a Group)
    g = Group()
    g.transform = (0, 1, -1, 0, 14, H / 2 - 20)
    g.add(String(0, 0, "Event count", fontSize=7, fontName="Helvetica-Oblique",
                  fillColor=_colors.HexColor("#475569"), textAnchor="middle"))
    d.add(g)

    # Mean line
    mean_val = _statistics.mean(exon_sizes)
    mean_idx = mean_val / BIN
    mean_x = MARGIN_L + mean_idx * (bar_w + 1)
    d.add(Line(mean_x, MARGIN_B, mean_x, MARGIN_B + chart_h,
                strokeColor=_colors.HexColor("#ef4444"), strokeWidth=1,
                strokeDashArray=[4, 2]))
    d.add(String(mean_x + 3, MARGIN_B + chart_h - 8, f"Mean {mean_val:.0f} nt",
                  fontSize=6, fontName="Helvetica", fillColor=_colors.HexColor("#ef4444")))

    # Median line
    med_val = _statistics.median(exon_sizes)
    med_idx = med_val / BIN
    med_x = MARGIN_L + med_idx * (bar_w + 1)
    d.add(Line(med_x, MARGIN_B, med_x, MARGIN_B + chart_h,
                strokeColor=_colors.HexColor("#f97316"), strokeWidth=1,
                strokeDashArray=[4, 2]))
    d.add(String(med_x + 3, MARGIN_B + chart_h - 18, f"Median {med_val:.0f} nt",
                  fontSize=6, fontName="Helvetica", fillColor=_colors.HexColor("#f97316")))

    # Axes
    d.add(Line(MARGIN_L, MARGIN_B, MARGIN_L + chart_w, MARGIN_B,
                strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8))
    d.add(Line(MARGIN_L, MARGIN_B, MARGIN_L, MARGIN_B + chart_h,
                strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8))

    return d


def _fig_frame_breakdown(n_if: int, n_fs: int, n_nc: int, n_feat: int) -> Drawing | None:
    """Horizontal stacked bar showing reading-frame class proportions."""
    if n_feat == 0:
        return None

    W, H = 440, 50
    BAR_Y, BAR_H = 18, 18
    MARGIN_L = 10

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_colors.HexColor("#fafafa"),
               strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.5))

    bar_w = W - 2 * MARGIN_L
    segments = [
        (n_if, "#22c55e", "In-frame"),
        (n_fs, "#ef4444", "Frameshift"),
        (n_nc, "#94a3b8", "Non-coding"),
    ]

    x = MARGIN_L
    for count, color, label in segments:
        if count == 0:
            continue
        seg_w = (count / n_feat) * bar_w
        d.add(Rect(x, BAR_Y, seg_w, BAR_H,
                    fillColor=_colors.HexColor(color), strokeColor=None))
        # Label inside if wide enough
        pct = count / n_feat * 100
        if seg_w > 35:
            d.add(String(x + seg_w / 2, BAR_Y + 5,
                          f"{label} {pct:.0f}%",
                          fontSize=6, fontName="Helvetica-Bold", fillColor=_colors.white,
                          textAnchor="middle"))
        x += seg_w

    # Legend below
    lx = MARGIN_L
    for count, color, label in segments:
        if count == 0:
            continue
        d.add(Rect(lx, 2, 8, 8, fillColor=_colors.HexColor(color), strokeColor=None))
        d.add(String(lx + 10, 2, f"{label}: {count} ({count / n_feat * 100:.1f}%)",
                      fontSize=5.5, fontName="Helvetica", fillColor=_colors.HexColor("#475569")))
        lx += 110

    return d


def _fig_dpsi_distribution(events: list, group1_label: str = "Group 1") -> Drawing | None:
    """ΔΨ distribution histogram for all events."""
    dpsi_vals = [e.inc_level_difference for e in events
                 if e.inc_level_difference is not None]
    if len(dpsi_vals) < 3:
        return None

    BIN_W = 0.1
    bins = {}  # rounded bin_start → count
    for v in dpsi_vals:
        b = round(_math.floor(v / BIN_W) * BIN_W, 2)
        bins[b] = bins.get(b, 0) + 1

    sorted_bins = sorted(bins.keys())
    counts = [bins[b] for b in sorted_bins]

    W, H = 440, 140
    MARGIN_L, MARGIN_B, MARGIN_T, MARGIN_R = 40, 28, 16, 20
    chart_w = W - MARGIN_L - MARGIN_R
    chart_h = H - MARGIN_B - MARGIN_T

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_colors.HexColor("#fafafa"),
               strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.5))

    max_count = max(counts) or 1
    n_bars = len(sorted_bins)
    bar_w = max(3, chart_w / n_bars - 1)

    for i, (b, cnt) in enumerate(zip(sorted_bins, counts)):
        bar_h = (cnt / max_count) * chart_h
        x = MARGIN_L + i * (bar_w + 1)
        color = "#ef4444" if b < 0 else "#3b82f6"
        d.add(Rect(x, MARGIN_B, bar_w, bar_h,
                    fillColor=_colors.HexColor(color),
                    strokeColor=None, fillOpacity=0.7))

    # Axes
    d.add(Line(MARGIN_L, MARGIN_B, MARGIN_L + chart_w, MARGIN_B,
                strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8))
    d.add(Line(MARGIN_L, MARGIN_B, MARGIN_L, MARGIN_B + chart_h,
                strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8))

    # X-axis labels
    for i, b in enumerate(sorted_bins):
        if i % max(1, n_bars // 8) == 0:
            x = MARGIN_L + i * (bar_w + 1) + bar_w / 2
            d.add(String(x, MARGIN_B - 12, f"{b:+.1f}",
                          fontSize=5.5, fontName="Helvetica", fillColor=_colors.HexColor("#475569"),
                          textAnchor="middle"))

    d.add(String(W / 2, 3, "ΔΨ (inclusion level difference)",
                  fontSize=7, fontName="Helvetica-Oblique", fillColor=_colors.HexColor("#475569"),
                  textAnchor="middle"))

    # Y-axis tick labels (0, max/2, max)
    for val in [0, max_count // 2, max_count]:
        y = MARGIN_B + (val / max_count) * chart_h
        d.add(String(MARGIN_L - 4, y - 2, str(val),
                      fontSize=6, fontName="Helvetica", fillColor=_colors.HexColor("#475569"),
                      textAnchor="end"))
        d.add(Line(MARGIN_L, y, MARGIN_L + chart_w, y,
                    strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.3))

    # Y-axis title
    g = Group()
    g.transform = (0, 1, -1, 0, 12, H / 2 - 20)
    g.add(String(0, 0, "Event count", fontSize=7, fontName="Helvetica-Oblique",
                  fillColor=_colors.HexColor("#475569"), textAnchor="middle"))
    d.add(g)

    # Zero line
    zero_i = None
    for i, b in enumerate(sorted_bins):
        if b >= 0:
            zero_i = i
            break
    if zero_i is not None:
        zx = MARGIN_L + zero_i * (bar_w + 1)
        d.add(Line(zx, MARGIN_B, zx, MARGIN_B + chart_h,
                    strokeColor=_colors.HexColor("#1e293b"), strokeWidth=0.8,
                    strokeDashArray=[3, 2]))

    # Legend (use actual group names)
    leg_w = 160
    d.add(Rect(W - leg_w, H - 14, 8, 8, fillColor=_colors.HexColor("#ef4444"), strokeColor=None))
    d.add(String(W - leg_w + 10, H - 14, f"ΔΨ < 0 (↑ skipping {group1_label})", fontSize=5.5,
                  fontName="Helvetica", fillColor=_colors.HexColor("#475569")))
    d.add(Rect(W - leg_w, H - 24, 8, 8, fillColor=_colors.HexColor("#3b82f6"), strokeColor=None))
    d.add(String(W - leg_w + 10, H - 24, f"ΔΨ > 0 (↑ inclusion {group1_label})", fontSize=5.5,
                  fontName="Helvetica", fillColor=_colors.HexColor("#475569")))

    return d


def _fig_splice_site_consensus(
    features_dict: dict,
    site: str = "donor",
    *,
    pwm_data: list[dict[str, float]] | None = None,
    n_sequences: int | None = None,
    max_width: float = 440,
) -> Drawing | None:
    """Frequency-mode sequence logo for donor (9 nt) or acceptor (23 nt).

    Every column fills the full logo height; letter height is proportional
    to raw nucleotide frequency only (no IC/bits scaling), matching the
    frequency view in the web app.

    If *pwm_data* is provided, it is used directly; otherwise PWM is computed
    from the splice features in *features_dict*.
    """

    if pwm_data:
        pwm = pwm_data
    else:
        sequences = []
        for f in features_dict.values():
            seq = f.donor_seq if site == "donor" else f.acceptor_seq
            if seq:
                expected_len = 9 if site == "donor" else 23
                if len(seq) >= expected_len:
                    sequences.append(seq[:expected_len].upper())
        if len(sequences) < 3:
            return None

        seq_len = len(sequences[0])
        pwm = []
        for pos in range(seq_len):
            counts = Counter(seq[pos] for seq in sequences)
            total = sum(counts[b] for b in "ACGT") or 1
            freqs = {b: counts.get(b, 0) / total for b in "ACGT"}
            pwm.append(freqs)

    seq_len = len(pwm)
    BASE_COLORS = {"A": "#22c55e", "C": "#3b82f6", "G": "#f97316", "T": "#ef4444"}

    COL_W  = min(22, int((max_width - 16) / seq_len))
    LOGO_H = 80
    MARGIN_L, MARGIN_B, MARGIN_T = 8, 24, 8
    W = min(max_width, MARGIN_L + seq_len * COL_W + 8)
    H = MARGIN_T + LOGO_H + MARGIN_B

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_colors.HexColor("#fafafa"),
               strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.5))

    start_pos = -3 if site == "donor" else -20
    canonical = {1, 2} if site == "donor" else {-2, -1}

    for col_idx, freqs in enumerate(pwm):
        x    = MARGIN_L + col_idx * COL_W
        pos  = start_pos + col_idx
        if pos >= 0:
            pos += 1

        # Yellow highlight for canonical GT/AG positions
        if pos in canonical:
            d.add(Rect(x, MARGIN_B, COL_W, LOGO_H,
                        fillColor=_colors.HexColor("#fef08a"), fillOpacity=0.35,
                        strokeColor=None))

        # Frequency mode: every column fills LOGO_H; letter height ∝ frequency
        sorted_bases = sorted(freqs.items(), key=lambda kv: kv[1])
        cur_y = MARGIN_B
        for base, freq in sorted_bases:
            if freq <= 0:
                continue
            h = freq * LOGO_H
            if h < 0.5:
                cur_y += h
                continue
            # Font size: fits letter glyph in its allocated band (ascent ≈ 75 % of fontSize)
            fs = min(h / 0.75, COL_W * 1.2)
            fs = max(fs, 4)
            d.add(String(
                x + COL_W / 2,
                cur_y + (h - fs * 0.75) / 2,
                base,
                fontSize=fs,
                fontName="Courier-Bold",
                fillColor=_colors.HexColor(BASE_COLORS[base]),
                textAnchor="middle",
            ))
            cur_y += h

        # Position label
        label     = f"+{pos}" if pos > 0 else str(pos)
        is_canon  = pos in canonical
        d.add(String(
            x + COL_W / 2, MARGIN_B - 12, label,
            fontSize=6 if not is_canon else 7,
            fontName="Courier-Bold" if is_canon else "Courier",
            fillColor=_colors.HexColor("#b45309") if is_canon else _colors.HexColor("#94a3b8"),
            textAnchor="middle",
        ))

    site_label = "5'SS donor position" if site == "donor" else "3'SS acceptor position"
    d.add(String(
        MARGIN_L + seq_len * COL_W / 2, 3, site_label,
        fontSize=7, fontName="Helvetica-Oblique",
        fillColor=_colors.HexColor("#475569"), textAnchor="middle",
    ))
    d.add(Line(
        MARGIN_L, MARGIN_B, MARGIN_L + seq_len * COL_W, MARGIN_B,
        strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8,
    ))

    return d


def _build_pdf(
    analysis,
    events: list,
    features: dict,
    group1_label: str = "Group 1",
    group2_label: str = "Group 2",
    *,
    deep_analysis=None,
    comparison=None,
    sig_map: dict | None = None,
    permutation_table: list[dict] | None = None,
    hnrnp_data: dict | None = None,
    enrichr_data: dict | None = None,
) -> bytes:
    """Build PDF report.

    Parameters
    ----------
    deep_analysis : DeepAnalysis | None
        If provided, the report is scoped to this deep analysis (its events).
    comparison : dict | None
        Pattern comparison data with keys: "significant", "not_significant",
        "statistical_tests" — same shape as PatternComparisonResponse.
    sig_map : dict | None
        Mapping of event_id → bool (is_significant).  Used to build
        the "Significant Events" section in deep-analysis reports.
    permutation_table : list[dict] | None
        ΔΨ permutation results at multiple iteration counts.
        Each dict: {"iterations": int, "n_tested": int,
                     "pct_p05": float, "pct_p01": float}.
    hnrnp_data : dict | None
        Result from hnRNP motif enrichment analysis.
        Keys: n_sig_events, n_bg_events, results (list of enrichment items).
    enrichr_data : dict | None
        Result from Enrichr pathway enrichment.
        Keys: n_genes_submitted, terms (list of EnrichrTermItem dicts).
    """
    # Thread-local figure counter: avoids data races when multiple PDF
    # requests are served concurrently via asyncio.to_thread.
    _fig_count: list[int] = [0]

    def _next_fig() -> int:
        _fig_count[0] += 1
        return _fig_count[0]

    buf = BytesIO()
    USABLE_W = _W - 2 * _MARGIN          # ~15.27 cm
    FIG_MAX_W = USABLE_W                  # figures must not exceed this

    doc = SimpleDocTemplate(
        buf, pagesize=_A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=_MARGIN,
    )
    S = _build_styles()
    story: list = []

    def p(text: str, style: str = "body") -> Paragraph:
        return Paragraph(text, S[style])

    def sp(h: float = 0.3) -> Spacer:
        return Spacer(1, h * _cm)

    def hr() -> HRFlowable:
        return HRFlowable(width="100%", thickness=0.5, color=_colors.HexColor("#e2e8f0"), spaceAfter=6)

    def caption(text: str) -> Paragraph:
        n = _next_fig()
        return Paragraph(
            f"<b>Figure {n}.</b> {text}",
            ParagraphStyle("Caption", parent=S["small"], spaceBefore=4, spaceAfter=10,
                           alignment=TA_CENTER, fontSize=7.5, leading=10,
                           textColor=_colors.HexColor("#475569")),
        )

    is_deep = deep_analysis is not None

    # ── Title page ──────────────────────────────────────────────────────────
    title = "rMATS-Viz Deep Analysis Report" if is_deep else "rMATS-Viz Analysis Report"
    story += [
        sp(3),
        p(title, "h1"),
        hr(),
        sp(0.3),
        p(f"<b>Analysis:</b> {analysis.name}", "body"),
        p(f"<b>Generated:</b> {_date.today().isoformat()}", "body"),
        p(f"<b>Identifier:</b> {analysis.id}", "small"),
    ]

    story.append(p(f"<b>Groups:</b> {group1_label} vs {group2_label}", "body"))

    if is_deep:
        story += [
            p(f"<b>Deep analysis:</b> {deep_analysis.name or '—'}", "body"),
            p(f"<b>Thresholds:</b> FDR ≤ {deep_analysis.fdr_threshold}, "
              f"|ΔΨ| ≥ {deep_analysis.delta_psi_min}", "body"),
        ]

    if analysis.mutated_genes:
        gene_names = ", ".join(g.get("symbol", "?") for g in analysis.mutated_genes if g.get("symbol"))
        if gene_names:
            story.append(p(f"<b>Candidate gene(s):</b> {gene_names}", "body"))

    # ── Summary statistics on title page ──────────────────────────────────
    n_total = len(events)
    se_evts_all = [e for e in events if e.event_type == "SE"]
    n_se = len(se_evts_all)
    n_with_seq = sum(1 for f in features.values() if f.donor_seq)
    n_gt = sum(1 for f in features.values() if f.donor_is_gt is True)
    n_ag = sum(1 for f in features.values() if f.acceptor_is_ag is True)
    story += [
        sp(0.3),
        p(f"<b>Total events:</b> {n_total} · <b>SE events:</b> {n_se}", "body"),
        p(f"<b>SE events with sequence data:</b> {n_with_seq} / {n_se}", "body"),
        p(f"<b>Canonical GT (5'SS):</b> {n_gt} / {n_with_seq} "
          f"({n_gt / n_with_seq * 100:.1f}%)" if n_with_seq else "", "body") if n_with_seq else sp(0),
        p(f"<b>Canonical AG (3'SS):</b> {n_ag} / {n_with_seq} "
          f"({n_ag / n_with_seq * 100:.1f}%)" if n_with_seq else "", "body") if n_with_seq else sp(0),
    ]

    story += [
        sp(0.5),
        p(
            "This report summarises the alternative splicing events identified "
            "by rMATS and annotated via rMATS-Viz (splice sites, reading frame, "
            "MANE transcript, PPT regions, branch point). "
            + ("Events are filtered by the deep analysis thresholds above. "
               if is_deep else "")
            + "All figures are vector graphics suitable for publication.",
            "body",
        ),
        PageBreak(),
    ]

    # ── Helper: build stats table + figures for a feature subset ──────────
    def _add_stats_and_figures(
        subset_features: dict,
        subset_events: list,
        section_num: int,
        section_title: str,
        include_figures: bool = True,
    ) -> int:
        """Append summary statistics table and (optionally) figures.

        Returns section_num + 1 for chaining.
        """
        nonlocal story
        story.append(p(f"{section_num}. {section_title}", "h2"))

        se_evts = [e for e in subset_events if e.event_type == "SE"]

        if not is_deep or section_num == 1:
            # Type breakdown only for the global section
            type_cnts: dict[str, int] = {}
            for ev in subset_events:
                type_cnts[ev.event_type] = type_cnts.get(ev.event_type, 0) + 1
            story += [
                p(f"Total events: <b>{len(subset_events)}</b>", "body"),
                p(f"SE events: <b>{len(se_evts)}</b> · "
                  f"RI: {type_cnts.get('RI', 0)} · "
                  f"A3SS: {type_cnts.get('A3SS', 0)} · "
                  f"A5SS: {type_cnts.get('A5SS', 0)} · "
                  f"MXE: {type_cnts.get('MXE', 0)}", "body"),
            ]
            type_tbl = Table(
                [["Type", "Event Count", "% of Total"]] +
                [
                    [etype,
                     type_cnts.get(etype, 0),
                     f"{type_cnts.get(etype, 0) / max(len(subset_events), 1) * 100:.1f}%"]
                    for etype in ["SE", "RI", "A3SS", "A5SS", "MXE"]
                ] +
                [[Paragraph("<b>Total</b>", S["body"]),
                  Paragraph(f"<b>{len(subset_events)}</b>", S["body"]),
                  Paragraph("<b>100%</b>", S["body"])]],
                colWidths=[4 * _cm, 4 * _cm, 4 * _cm],
            )
            type_tbl.setStyle(_tbl_style())
            story += [sp(), type_tbl, sp()]

        if subset_features:
            n_f  = len(subset_features)
            n_gt = sum(1 for f in subset_features.values() if f.donor_is_gt is True)
            n_ag = sum(1 for f in subset_features.values() if f.acceptor_is_ag is True)
            n_if = sum(1 for f in subset_features.values() if f.frame_class == "in_frame")
            n_fs = sum(1 for f in subset_features.values() if f.frame_class == "frameshift")
            n_nc = sum(1 for f in subset_features.values() if f.frame_class == "non_coding")
            n_bp = sum(1 for f in subset_features.values() if f.bp_motif_found is True)
            n_up_gt = sum(1 for f in subset_features.values() if f.upstream_donor_is_gt is True)
            n_up_seq = sum(1 for f in subset_features.values() if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9)
            n_dn_ag = sum(1 for f in subset_features.values() if f.downstream_acceptor_is_ag is True)
            n_dn_seq = sum(1 for f in subset_features.values() if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23)
            ppt_vals = [f.ppt_score for f in subset_features.values() if f.ppt_score is not None]
            exsz_vals = [f.exon_size for f in subset_features.values() if f.exon_size is not None]

            story.append(p("SE Splice Feature Statistics:", "h3"))
            stat_tbl = Table([
                ["Metric", "Value"],
                ["SE events with features", n_f],
                ["Canonical GT (5'SS)", f"{n_gt} / {n_f} ({n_gt / n_f * 100:.1f}%)" if n_f else "—"],
                ["Canonical AG (3'SS)", f"{n_ag} / {n_f} ({n_ag / n_f * 100:.1f}%)" if n_f else "—"],
                ["Upstream GT (5'SS)", f"{n_up_gt} / {n_up_seq} ({n_up_gt / n_up_seq * 100:.1f}%)" if n_up_seq else "—"],
                ["Downstream AG (3'SS)", f"{n_dn_ag} / {n_dn_seq} ({n_dn_ag / n_dn_seq * 100:.1f}%)" if n_dn_seq else "—"],
                ["In-frame",   f"{n_if} ({n_if / n_f * 100:.0f}%)" if n_f else "—"],
                ["Frameshift", f"{n_fs} ({n_fs / n_f * 100:.0f}%)" if n_f else "—"],
                ["Non-coding", f"{n_nc} ({n_nc / n_f * 100:.0f}%)" if n_f else "—"],
                ["Branch point detected", f"{n_bp} / {n_f} ({n_bp / n_f * 100:.1f}%)" if n_f else "—"],
                ["Exon size (mean / median)",
                 f"{_statistics.mean(exsz_vals):.0f} / {_statistics.median(exsz_vals):.0f} nt" if exsz_vals else "—"],
                ["Mean PPT score",
                 f"{_statistics.mean(ppt_vals) * 100:.1f}% pyrimidine content" if ppt_vals else "—"],
            ], colWidths=[9 * _cm, 7 * _cm])
            stat_tbl.setStyle(_tbl_style())
            story += [stat_tbl, sp()]

            if include_figures:
                dpsi_fig = _fig_dpsi_distribution(subset_events, group1_label)
                if dpsi_fig:
                    story += [
                        KeepTogether([
                            dpsi_fig,
                            caption(
                                "Distribution of ΔΨ (inclusion level difference). "
                                f"Red bars: ΔΨ &lt; 0 (more exon skipping in {group1_label}); "
                                f"blue bars: ΔΨ &gt; 0 (more exon inclusion in {group1_label}). "
                                f"n = {len(subset_events)} events."
                            ),
                        ]),
                        sp(),
                    ]

                hist_fig = _fig_exon_size_histogram(exsz_vals)
                if hist_fig:
                    story += [
                        KeepTogether([
                            hist_fig,
                            caption(
                                f"Skipped exon size distribution (25 nt bins). "
                                f"Mean = {_statistics.mean(exsz_vals):.0f} nt (red dashed), "
                                f"median = {_statistics.median(exsz_vals):.0f} nt (orange dashed). "
                                f"n = {len(exsz_vals)} SE events."
                            ),
                        ]),
                        sp(),
                    ]

                frame_fig = _fig_frame_breakdown(n_if, n_fs, n_nc, n_f)
                if frame_fig:
                    story += [
                        KeepTogether([
                            frame_fig,
                            caption(
                                "Reading-frame classification of skipped exons. "
                                "In-frame: CDS length divisible by 3; frameshift: not divisible by 3; "
                                f"non-coding: exon entirely within UTR. n = {n_f} SE events."
                            ),
                        ]),
                        sp(),
                    ]

                n_donor = sum(1 for f in subset_features.values() if f.donor_seq and len(f.donor_seq) >= 9)
                donor_logo = _fig_splice_site_consensus(subset_features, site="donor", n_sequences=n_donor, max_width=FIG_MAX_W)
                if donor_logo:
                    story += [
                        KeepTogether([
                            donor_logo,
                            caption(
                                "Skipped exon 5'SS donor splice site sequence logo (9 nt: 3 nt exon + 6 nt intron). "
                                "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
                                "e<sub>n</sub> = (s-1)/(2 ln2 n). Canonical GT at positions +1/+2 highlighted in yellow. "
                                f"n = {n_donor} sequences. "
                                "Schneider &amp; Stephens (1990); Crooks et al. (2004)."
                            ),
                        ]),
                        sp(),
                    ]

                n_acc = sum(1 for f in subset_features.values() if f.acceptor_seq and len(f.acceptor_seq) >= 23)
                acceptor_logo = _fig_splice_site_consensus(subset_features, site="acceptor", n_sequences=n_acc, max_width=FIG_MAX_W)
                if acceptor_logo:
                    story += [
                        KeepTogether([
                            acceptor_logo,
                            caption(
                                "Skipped exon 3'SS acceptor splice site sequence logo (23 nt: 20 nt intron + 3 nt exon). "
                                "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
                                "Canonical AG at positions -2/-1 highlighted in yellow. "
                                f"n = {n_acc} sequences. "
                                "Schneider &amp; Stephens (1990); Crooks et al. (2004)."
                            ),
                        ]),
                        sp(),
                    ]

                # Flanking exon — upstream donor 5'SS
                up_seqs = [f.upstream_donor_seq[:9].upper() for f in subset_features.values()
                           if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9]
                if len(up_seqs) >= 3:
                    up_pwm = []
                    for pos_i in range(9):
                        cnt = Counter(s[pos_i] for s in up_seqs)
                        tot = sum(cnt[b] for b in "ACGT") or 1
                        up_pwm.append({b: cnt.get(b, 0) / tot for b in "ACGT"})
                    up_logo = _fig_splice_site_consensus(
                        {}, site="donor", pwm_data=up_pwm,
                        n_sequences=len(up_seqs), max_width=FIG_MAX_W,
                    )
                    if up_logo:
                        story += [
                            KeepTogether([
                                up_logo,
                                caption(
                                    "Upstream flanking exon donor (5'SS) sequence logo (9 nt: 3 nt exon + 6 nt intron). "
                                    "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
                                    "Canonical GT at positions +1/+2 highlighted in yellow. "
                                    f"n = {len(up_seqs)} sequences."
                                ),
                            ]),
                            sp(),
                        ]

                # Flanking exon — downstream acceptor 3'SS
                dn_seqs = [f.downstream_acceptor_seq[-23:].upper() for f in subset_features.values()
                           if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23]
                if len(dn_seqs) >= 3:
                    dn_pwm = []
                    for pos_i in range(23):
                        cnt = Counter(s[pos_i] for s in dn_seqs)
                        tot = sum(cnt[b] for b in "ACGT") or 1
                        dn_pwm.append({b: cnt.get(b, 0) / tot for b in "ACGT"})
                    dn_logo = _fig_splice_site_consensus(
                        {}, site="acceptor", pwm_data=dn_pwm,
                        n_sequences=len(dn_seqs), max_width=FIG_MAX_W,
                    )
                    if dn_logo:
                        story += [
                            KeepTogether([
                                dn_logo,
                                caption(
                                    "Downstream flanking exon acceptor (3'SS) sequence logo (23 nt: 20 nt intron + 3 nt exon). "
                                    "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
                                    "Canonical AG at positions -2/-1 highlighted in yellow. "
                                    f"n = {len(dn_seqs)} sequences."
                                ),
                            ]),
                            sp(),
                        ]

        return section_num + 1

    # ── Section A: Global Analysis Summary ─────────────────────────────────
    section_n = _add_stats_and_figures(features, events, 1, "Global Analysis Summary")

    # ── Section B: Significant Events (deep analysis only) ─────────────────
    if is_deep and sig_map:
        story.append(PageBreak())
        sig_feat_dict = {eid: f for eid, f in features.items() if sig_map.get(eid)}
        sig_evts = [e for e in events if sig_map.get(e.id)]
        section_n = _add_stats_and_figures(
            sig_feat_dict, sig_evts, section_n,
            f"Significant Events (FDR ≤ {deep_analysis.fdr_threshold}, |ΔΨ| ≥ {deep_analysis.delta_psi_min})",
        )

    # ── Section C: Comparison (deep analysis only) ─────────────────────────
    if comparison:
        story.append(PageBreak())
        cmp_sec = section_n
        story.append(p(f"{cmp_sec}. Significant vs Non-Significant Comparison", "h2"))
        section_n += 1

        sig = comparison["significant"]
        nonsig = comparison["not_significant"]
        tests = comparison.get("statistical_tests", [])
        test_map = {t["feature"]: t for t in tests}

        def _fmt_pval(pv):
            if pv is None:
                return "—"
            if pv < 0.0001:
                return f"{pv:.2e}"
            return f"{pv:.4f}"

        def _sig_str(t):
            if t is None:
                return ""
            return "★" if t.get("significant") else "n.s."

        # Ca. Feature comparison table
        cmp_headers = ["Feature", f"Significant (n={sig['n_se_with_features']})",
                        f"Non-significant (n={nonsig['n_se_with_features']})", "Test", "p-value", ""]
        cmp_rows = [cmp_headers]

        def _row(label, sig_val, nonsig_val, test_key):
            t = test_map.get(test_key)
            cmp_rows.append([
                label,
                sig_val if sig_val is not None else "—",
                nonsig_val if nonsig_val is not None else "—",
                t["test_name"] if t else "—",
                _fmt_pval(t["p_value"] if t else None),
                _sig_str(t),
            ])

        def _pct(v):
            return f"{v:.1f}%" if v is not None else "—"

        _row("Exon size (mean)", f"{sig['exon_size_mean']:.0f} nt" if sig.get("exon_size_mean") else "—",
             f"{nonsig['exon_size_mean']:.0f} nt" if nonsig.get("exon_size_mean") else "—", "exon_size")
        _row("Canonical GT", _pct(sig.get("pct_canonical_gt")), _pct(nonsig.get("pct_canonical_gt")), "canonical_gt")
        _row("Canonical AG", _pct(sig.get("pct_canonical_ag")), _pct(nonsig.get("pct_canonical_ag")), "canonical_ag")
        _row("Mean PPT score", _pct(sig["ppt_mean_score"] * 100 if sig.get("ppt_mean_score") is not None else None),
             _pct(nonsig["ppt_mean_score"] * 100 if nonsig.get("ppt_mean_score") is not None else None), "ppt_score")
        _row("In-frame %", _pct(sig["frame_in_frame"] / max(sig["n_se_with_features"], 1) * 100 if sig["n_se_with_features"] else None),
             _pct(nonsig["frame_in_frame"] / max(nonsig["n_se_with_features"], 1) * 100 if nonsig["n_se_with_features"] else None), "in_frame_pct")
        _row("Branch point found", _pct(sig.get("bp_found_pct")), _pct(nonsig.get("bp_found_pct")), "bp_found")
        _row("Mean ΔΨ",
             f"{sig['mean_delta_psi']:+.3f}" if sig.get("mean_delta_psi") is not None else "—",
             f"{nonsig['mean_delta_psi']:+.3f}" if nonsig.get("mean_delta_psi") is not None else "—",
             "mean_delta_psi")
        _row("Upstream GT (5'SS)", _pct(sig.get("pct_upstream_gt")), _pct(nonsig.get("pct_upstream_gt")), "upstream_canonical_gt")
        _row("Downstream AG (3'SS)", _pct(sig.get("pct_downstream_ag")), _pct(nonsig.get("pct_downstream_ag")), "downstream_canonical_ag")

        cmp_tbl = Table(cmp_rows, colWidths=[3.2*_cm, 3.5*_cm, 3.5*_cm, 2.8*_cm, 2.2*_cm, 1*_cm])
        cmp_tbl.setStyle(_tbl_style())
        story += [KeepTogether([
            p(f"{cmp_sec}.1 Feature Comparison", "h3"),
            cmp_tbl,
            p("★ = p &lt; 0.05; n.s. = not significant", "small"),
        ]), sp()]

        # Cb. Comparison logos — donor
        half_w = FIG_MAX_W * 0.48
        _block: list = [p(f"{cmp_sec}.2 5'SS Donor Logo: Significant vs Non-Significant", "h3")]
        if sig.get("donor_pwm"):
            d_sig = _fig_splice_site_consensus(
                {}, site="donor", pwm_data=sig["donor_pwm"],
                n_sequences=sig["n_se_with_features"], max_width=half_w,
            )
            if d_sig:
                _block += [
                    p(f"<b>Significant</b> (n = {sig['n_se_with_features']})", "small"),
                    d_sig,
                ]
        if nonsig.get("donor_pwm"):
            d_nonsig = _fig_splice_site_consensus(
                {}, site="donor", pwm_data=nonsig["donor_pwm"],
                n_sequences=nonsig["n_se_with_features"], max_width=half_w,
            )
            if d_nonsig:
                _block += [
                    p(f"<b>Non-significant</b> (n = {nonsig['n_se_with_features']})", "small"),
                    d_nonsig,
                ]
        t_gt = test_map.get("canonical_gt")
        if t_gt:
            _block.append(p(
                f"Canonical GT proportion — {t_gt['test_name']}: "
                f"p = {_fmt_pval(t_gt['p_value'])} "
                f"({'significant' if t_gt['significant'] else 'not significant'})",
                "small",
            ))
        _block.append(caption(
            "Skipped exon 5'SS donor sequence logos: significant vs non-significant events. "
            "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
            "Canonical GT at positions +1/+2 highlighted. "
            "Schneider &amp; Stephens (1990); Crooks et al. (2004)."
        ))
        story += [KeepTogether(_block), sp()]

        # Cc. Comparison logos — acceptor
        _block = [p(f"{cmp_sec}.3 3'SS Acceptor Logo: Significant vs Non-Significant", "h3")]
        if sig.get("acceptor_pwm"):
            a_sig = _fig_splice_site_consensus(
                {}, site="acceptor", pwm_data=sig["acceptor_pwm"],
                n_sequences=sig["n_se_with_features"], max_width=half_w,
            )
            if a_sig:
                _block += [
                    p(f"<b>Significant</b> (n = {sig['n_se_with_features']})", "small"),
                    a_sig,
                ]
        if nonsig.get("acceptor_pwm"):
            a_nonsig = _fig_splice_site_consensus(
                {}, site="acceptor", pwm_data=nonsig["acceptor_pwm"],
                n_sequences=nonsig["n_se_with_features"], max_width=half_w,
            )
            if a_nonsig:
                _block += [
                    p(f"<b>Non-significant</b> (n = {nonsig['n_se_with_features']})", "small"),
                    a_nonsig,
                ]
        t_ag = test_map.get("canonical_ag")
        if t_ag:
            _block.append(p(
                f"Canonical AG proportion — {t_ag['test_name']}: "
                f"p = {_fmt_pval(t_ag['p_value'])} "
                f"({'significant' if t_ag['significant'] else 'not significant'})",
                "small",
            ))
        _block.append(caption(
            "Skipped exon 3'SS acceptor sequence logos: significant vs non-significant events. "
            "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
            "Canonical AG at positions -2/-1 highlighted. "
            "Schneider &amp; Stephens (1990); Crooks et al. (2004)."
        ))
        story += [KeepTogether(_block), sp()]

        # Cd. Flanking exon — upstream donor (5'SS)
        if sig.get("upstream_donor_pwm") or nonsig.get("upstream_donor_pwm"):
            _block = [p(f"{cmp_sec}.4 Upstream Donor 5'SS Logo: Significant vs Non-Significant", "h3")]
            if sig.get("upstream_donor_pwm"):
                ud_sig = _fig_splice_site_consensus(
                    {}, site="donor", pwm_data=sig["upstream_donor_pwm"],
                    n_sequences=sig["n_se_with_features"], max_width=half_w,
                )
                if ud_sig:
                    _block += [
                        p(f"<b>Significant</b> (n = {sig['n_se_with_features']})", "small"),
                        ud_sig,
                    ]
            if nonsig.get("upstream_donor_pwm"):
                ud_nonsig = _fig_splice_site_consensus(
                    {}, site="donor", pwm_data=nonsig["upstream_donor_pwm"],
                    n_sequences=nonsig["n_se_with_features"], max_width=half_w,
                )
                if ud_nonsig:
                    _block += [
                        p(f"<b>Non-significant</b> (n = {nonsig['n_se_with_features']})", "small"),
                        ud_nonsig,
                    ]
            t_up_gt = test_map.get("upstream_canonical_gt")
            if t_up_gt:
                _block.append(p(
                    f"Upstream canonical GT — {t_up_gt['test_name']}: "
                    f"p = {_fmt_pval(t_up_gt['p_value'])} "
                    f"({'significant' if t_up_gt['significant'] else 'not significant'})",
                    "small",
                ))
            _block.append(caption(
                "Upstream flanking exon 5'SS donor sequence logos: significant vs non-significant events. "
                "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
                "Canonical GT at positions +1/+2 highlighted."
            ))
            story += [KeepTogether(_block), sp()]

        # Ce. Flanking exon — downstream acceptor (3'SS)
        if sig.get("downstream_acceptor_pwm") or nonsig.get("downstream_acceptor_pwm"):
            _block = [p(f"{cmp_sec}.5 Downstream Acceptor 3'SS Logo: Significant vs Non-Significant", "h3")]
            if sig.get("downstream_acceptor_pwm"):
                da_sig = _fig_splice_site_consensus(
                    {}, site="acceptor", pwm_data=sig["downstream_acceptor_pwm"],
                    n_sequences=sig["n_se_with_features"], max_width=half_w,
                )
                if da_sig:
                    _block += [
                        p(f"<b>Significant</b> (n = {sig['n_se_with_features']})", "small"),
                        da_sig,
                    ]
            if nonsig.get("downstream_acceptor_pwm"):
                da_nonsig = _fig_splice_site_consensus(
                    {}, site="acceptor", pwm_data=nonsig["downstream_acceptor_pwm"],
                    n_sequences=nonsig["n_se_with_features"], max_width=half_w,
                )
                if da_nonsig:
                    _block += [
                        p(f"<b>Non-significant</b> (n = {nonsig['n_se_with_features']})", "small"),
                        da_nonsig,
                    ]
            t_dn_ag = test_map.get("downstream_canonical_ag")
            if t_dn_ag:
                _block.append(p(
                    f"Downstream canonical AG — {t_dn_ag['test_name']}: "
                    f"p = {_fmt_pval(t_dn_ag['p_value'])} "
                    f"({'significant' if t_dn_ag['significant'] else 'not significant'})",
                    "small",
                ))
            _block.append(caption(
                "Downstream flanking exon 3'SS acceptor sequence logos: significant vs non-significant events. "
                "Letter height ∝ nucleotide frequency (frequency mode, columns always full height). "
                "Canonical AG at positions -2/-1 highlighted."
            ))
            story += [KeepTogether(_block), sp()]

        # Cf. Frame comparison
        _block = [p(f"{cmp_sec}.6 Reading Frame Comparison", "h3")]
        frame_sig = _fig_frame_breakdown(sig["frame_in_frame"], sig["frame_frameshift"], sig["frame_non_coding"], sig["n_se_with_features"])
        if frame_sig:
            _block += [p(f"<b>Significant</b> (n = {sig['n_se_with_features']})", "small"), frame_sig]
        frame_nonsig = _fig_frame_breakdown(nonsig["frame_in_frame"], nonsig["frame_frameshift"], nonsig["frame_non_coding"], nonsig["n_se_with_features"])
        if frame_nonsig:
            _block += [p(f"<b>Non-significant</b> (n = {nonsig['n_se_with_features']})", "small"), frame_nonsig]
        t_frame = test_map.get("in_frame_pct")
        if t_frame:
            _block.append(p(
                f"In-frame proportion — {t_frame['test_name']}: "
                f"p = {_fmt_pval(t_frame['p_value'])} "
                f"({'significant' if t_frame['significant'] else 'not significant'})",
                "small",
            ))
        _block.append(caption("Reading-frame breakdown: significant vs non-significant events."))
        story += [KeepTogether(_block), sp()]

    # ── Section D: Permutation Test (deep analysis only) ──────────────────
    if permutation_table:
        story.append(PageBreak())
        perm_sec = section_n
        story.append(p(f"{perm_sec}. Permutation Test — ΔΨ Significance", "h2"))
        section_n += 1

        story.append(p(
            "The permutation test evaluates whether the observed ΔΨ for each event is "
            "statistically significant by randomly permuting sample labels and computing "
            "a null distribution.  The table below shows the percentage of events reaching "
            "significance at different iteration counts, providing insight into result "
            "stability as the number of permutations increases.",
            "body",
        ))
        story.append(sp())

        perm_headers = ["Iterations", "Events Tested", "% p < 0.05", "% p < 0.01"]
        perm_rows = [perm_headers]
        for pt in permutation_table:
            perm_rows.append([
                f"{pt['iterations']:,}",
                f"{pt['n_tested']:,}",
                f"{pt['pct_p05']:.1f}%" if pt.get("pct_p05") is not None else "—",
                f"{pt['pct_p01']:.1f}%" if pt.get("pct_p01") is not None else "—",
            ])
        perm_tbl = Table(perm_rows, colWidths=[3.5 * _cm, 3.5 * _cm, 4 * _cm, 4 * _cm])
        perm_tbl.setStyle(_tbl_style())
        story += [perm_tbl, sp()]

        story.append(p(
            "As the number of permutation iterations increases, the empirical p-value "
            "estimates become more precise.  Convergence of the significance percentages "
            "across iterations indicates stable results.",
            "small",
        ))
        story.append(sp())

    # ── Section E: hnRNP Motif Enrichment (deep analysis only) ─────────────
    if hnrnp_data:
        story.append(PageBreak())
        hnrnp_sec = section_n
        section_n += 1
        story.append(p(f"{hnrnp_sec}. hnRNP Motif Enrichment Analysis", "h2"))
        story.append(p(
            "Inspired by rMAPS2 (Hwang et al., 2020), this analysis scans five genomic regions "
            "around each skipped exon for known hnRNP RNA-binding protein consensus motifs "
            "and compares their frequency between significant and non-significant events using "
            "a two-proportion z-test with Bonferroni correction.",
            "body",
        ))

        n_sig_e = hnrnp_data.get("n_sig_events", 0)
        n_bg_e = hnrnp_data.get("n_bg_events", 0)
        story.append(p(
            f"Significant events: <b>{n_sig_e}</b> · "
            f"Background events: <b>{n_bg_e}</b>",
            "body",
        ))
        story.append(sp(0.2))

        sig_motifs = [r for r in hnrnp_data.get("results", []) if r.get("significant")]
        if sig_motifs:
            # Sort by p_adjusted ascending
            sig_motifs_sorted = sorted(
                sig_motifs,
                key=lambda r: (r.get("p_adjusted") or 1.0, r.get("region", ""), r.get("motif_name", "")),
            )
            _region_labels = {
                "upstream_exon": "Upstream exon",
                "upstream_intron": "Upstream intron",
                "skipped_exon": "Skipped exon",
                "downstream_intron": "Downstream intron",
                "downstream_exon": "Downstream exon",
            }
            hnrnp_headers = ["Protein", "Motif", "Region", "Sig %", "Bg %", "z", "p (adj)"]
            hnrnp_rows = [hnrnp_headers]
            for r in sig_motifs_sorted[:20]:  # top 20
                sig_pct = f"{r['sig_hit_count'] / r['sig_total'] * 100:.1f}%" if r.get("sig_total") else "—"
                bg_pct = f"{r['bg_hit_count'] / r['bg_total'] * 100:.1f}%" if r.get("bg_total") else "—"
                p_adj = r.get("p_adjusted")
                p_str = f"{p_adj:.2e}" if p_adj is not None and p_adj < 0.001 else (f"{p_adj:.4f}" if p_adj is not None else "—")
                z_str = f"{r['z_stat']:.2f}" if r.get("z_stat") is not None else "—"
                hnrnp_rows.append([
                    r.get("protein", "—"),
                    r.get("motif_name", "—"),
                    _region_labels.get(r.get("region", ""), r.get("region", "—")),
                    sig_pct,
                    bg_pct,
                    z_str,
                    p_str,
                ])
            hnrnp_tbl = Table(hnrnp_rows, colWidths=[3.0*_cm, 1.8*_cm, 3.5*_cm, 1.8*_cm, 1.8*_cm, 1.5*_cm, 2.0*_cm])
            hnrnp_tbl.setStyle(_tbl_style())
            story += [hnrnp_tbl, sp(0.2)]
            story.append(p(
                f"Showing {min(len(sig_motifs_sorted), 20)} of {len(sig_motifs)} significant motif-region "
                "associations (Bonferroni-corrected p &lt; 0.05). "
                "Sig % / Bg % = percentage of events with at least one motif hit.",
                "small",
            ))
        else:
            story.append(p(
                "No motif-region combinations reached significance after Bonferroni correction.",
                "body",
            ))
        story.append(sp())

    # ── Section F: Enrichr Pathway Enrichment (deep analysis only) ─────────
    if enrichr_data and enrichr_data.get("terms"):
        story.append(PageBreak())
        enr_sec = section_n
        section_n += 1
        n_genes = enrichr_data.get("n_genes_submitted", 0)
        story.append(p(f"{enr_sec}. Pathway Enrichment Analysis (Enrichr)", "h2"))
        story.append(p(
            f"Gene symbols from significant events (n = {n_genes} unique genes) were submitted "
            "to the Enrichr REST API (Ma'ayan Lab). Enrichment was computed against five curated "
            "gene-set libraries: KEGG 2021, GO Biological Process, GO Molecular Function, "
            "Reactome 2022, and WikiPathways 2023. The combined score = |z-score| × log(p-value) "
            "(Chen et al., 2013).",
            "body",
        ))
        story.append(sp(0.2))

        _lib_labels = {
            "KEGG_2021_Human": "KEGG 2021",
            "GO_Biological_Process_2023": "GO Biol. Process",
            "GO_Molecular_Function_2023": "GO Mol. Function",
            "Reactome_2022": "Reactome 2022",
            "WikiPathway_2023_Human": "WikiPathways 2023",
        }
        # Show top 5 per library
        by_lib: dict[str, list] = {}
        for term in enrichr_data.get("terms", []):
            lib = term.get("library", "Unknown")
            by_lib.setdefault(lib, []).append(term)

        for lib, terms in by_lib.items():
            top_terms = sorted(terms, key=lambda t: t.get("adjusted_p_value", 1.0))[:5]
            lib_label = _lib_labels.get(lib, lib)
            story.append(p(lib_label, "h3"))
            enr_headers = ["Rank", "Term", "Overlap", "Adj. p-value", "Combined Score"]
            enr_rows = [enr_headers]
            for term in top_terms:
                adj_p = term.get("adjusted_p_value", 1.0)
                p_str = f"{adj_p:.2e}" if adj_p < 0.001 else f"{adj_p:.4f}"
                enr_rows.append([
                    str(term.get("rank", "—")),
                    str(term.get("term", "—")),
                    str(term.get("overlap", "—")),
                    p_str,
                    f"{term.get('combined_score', 0.0):.1f}",
                ])
            enr_tbl = Table(enr_rows, colWidths=[1.0*_cm, 7.5*_cm, 1.8*_cm, 2.2*_cm, 2.7*_cm])
            enr_tbl.setStyle(_tbl_style())
            story += [enr_tbl, sp(0.2)]
        story.append(p(
            "FDR-adjusted p-values use the Benjamini-Hochberg method (Enrichr internal correction). "
            "Top 5 terms per library shown.",
            "small",
        ))
        story.append(sp())

    # ── Top SE events ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(p(f"{section_n}. Top SE Events (ranked by FDR, |ΔΨ|)", "h2"))
    top_se = sorted(
        [e for e in events if e.event_type == "SE" and e.fdr is not None],
        key=lambda e: (e.fdr or 1, -(abs(e.inc_level_difference or 0))),
    )[:20]

    if top_se:
        top_headers = ["Gene", "Chr", "Strand", "Exon\nSize", "FDR", "ΔΨ", "GT-AG", "Frame"]
        top_rows = [top_headers]
        for ev in top_se:
            feat = features.get(ev.id)
            gt_ag = "—"
            if feat:
                gt = "GT" if feat.donor_is_gt else "!GT"
                ag = "AG" if feat.acceptor_is_ag else "!AG"
                gt_ag = f"{gt}/{ag}"
            top_rows.append([
                ev.gene_symbol or "—",
                ev.chr or "—",
                ev.strand or "—",
                str(feat.exon_size) + " nt" if feat and feat.exon_size else "—",
                f"{ev.fdr:.2e}" if ev.fdr is not None else "—",
                f"{ev.inc_level_difference:+.3f}" if ev.inc_level_difference is not None else "—",
                gt_ag,
                feat.frame_class or "—" if feat else "—",
            ])
        top_tbl = Table(top_rows, colWidths=[2.8*_cm, 1.8*_cm, 1*_cm, 1.8*_cm, 2.2*_cm, 1.8*_cm, 1.8*_cm, 2*_cm])
        top_tbl.setStyle(_tbl_style())
        story += [top_tbl, sp()]
    else:
        story.append(p("No SE events available.", "body"))

    story.append(PageBreak())

    # ── Appendix A — Methodology ────────────────────────────────────────────
    story += [
        p("Appendix A — Pipeline Methodology", "h2"),
        hr(),
        p("<b>1. Splicing Event Detection — rMATS</b>", "h3"),
        p("Alternative splicing events (SE, RI, A3SS, A5SS, MXE) are detected by "
          "<b>rMATS</b> (Shen et al., 2014) from aligned RNA-seq data. rMATS applies "
          "a multivariate uniform prior with a Bayesian framework to compute the "
          "posterior probability that ΔΨ exceeds a cutoff (default 0). Junction and "
          "exon-body read counts are combined in the JCEC model, while JC mode uses "
          "junction reads only. Output files used here are junction counts "
          "(<i>.MATS.JC.txt</i>).", "body"),
        p("<b>2. Splice Site Annotation</b>", "h3"),
        p("For each SE event, rMATS-Viz extracts flanking genomic sequences from "
          "the GRCh38 (hg38) reference genome indexed with <b>samtools faidx</b>:", "body"),
        p("• <b>5'SS donor (skipped exon):</b> 3 nt exon + 6 nt intron (9 nt window)", "body"),
        p("• <b>3'SS acceptor (skipped exon):</b> 20 nt intron + 3 nt exon (23 nt window)", "body"),
        p("• <b>5'SS donor (upstream flanking exon):</b> 3 nt exon + 6 nt intron (9 nt window)", "body"),
        p("• <b>3'SS acceptor (downstream flanking exon):</b> 20 nt intron + 3 nt exon (23 nt window)", "body"),
        p("• <b>PPT:</b> ~47 nt upstream of the skipped exon acceptor site", "body"),
        p("The canonical GT-AG splice site rule (Shapiro &amp; Senapathy, 1987; "
          "Burge &amp; Karlin, 1997) is verified at the first two intronic positions "
          "of the 5'SS (GT at +1/+2) and last two of the 3'SS (AG at -2/-1). "
          "The PPT score is the fraction of pyrimidine nucleotides (C, T) in the PPT "
          "window. The branch point is searched by matching the YNYURAY motif "
          "(Coolidge et al., 1997).", "body"),
        p("<b>3. Sequence Logos</b>", "h3"),
        p("Position weight matrices (PWMs) are computed from all extracted "
          "sequences per group. Logos are displayed in <b>frequency mode</b>: "
          "every column fills the full logo height, and the height of each letter "
          "is proportional to the raw nucleotide frequency f(b,i) at that position. "
          "No information-content (bits) scaling is applied, making each column "
          "directly comparable across positions regardless of conservation level. "
          "Canonical splice-site positions (GT at +1/+2 for donor; AG at -2/-1 for "
          "acceptor) are highlighted in yellow.", "body"),
        p("<b>4. Reading Frame Classification</b>", "h3"),
        p("The skipped exon is classified by reading-frame impact using the "
          "MANE Select transcript (Morales et al., 2022) when available:", "body"),
        p("• <b>in_frame:</b> CDS length divisible by 3 — protein domain loss without frameshift", "body"),
        p("• <b>frameshift:</b> CDS length not divisible by 3 — likely NMD or truncated protein", "body"),
        p("• <b>non_coding:</b> exon entirely within UTR — regulatory impact", "body"),
        p("<b>5. MANE Select Annotation</b>", "h3"),
        p("The MANE Select transcript is identified via the Ensembl REST API "
          "(Cunningham et al., 2022). The skipped exon is mapped to transcript "
          "coordinates to determine exon rank, CDS overlap, and frame impact. "
          "Results are cached in a local SQLite database.", "body"),
    ]
    if is_deep:
        story += [
            p("<b>6. Deep Analysis</b>", "h3"),
            p(f"Events are classified as <b>significant</b> (FDR ≤ {deep_analysis.fdr_threshold}, "
              f"|ΔΨ| ≥ {deep_analysis.delta_psi_min}) or <b>non-significant</b> (all others). "
              "Splice features are compared between the two groups using:", "body"),
            p("• <b>Welch's t-test</b> (unequal variances, two-tailed): mean ΔΨ, exon size, PPT score", "body"),
            p("• <b>Two-proportion z-test</b> (two-tailed): canonical GT/AG rates (skipped exon "
              "and flanking exons), in-frame proportion, branch-point detection rate", "body"),
            p("Welch-Satterthwaite degrees of freedom are used for the t-distribution. "
              "No multiple-testing correction is applied within the comparison (9 tests); "
              "the user should interpret results in light of the number of comparisons.", "body"),
            p("<b>7. Permutation Test</b>", "h3"),
            p("For each significant SE event, sample labels are randomly permuted (keeping "
              "group sizes fixed) to build a null distribution of ΔΨ. The empirical two-tailed "
              "p-value equals the fraction of permuted |ΔΨ| values ≥ the observed |ΔΨ|, "
              "plus one (Phipson &amp; Smyth, 2010 [13]). The test is run at multiple iteration "
              "counts (50, 100, 250, 500) to assess convergence.", "body"),
            p("<b>8. hnRNP Motif Enrichment Analysis</b>", "h3"),
            p("RNA-binding protein (RBP) motif enrichment is computed in a rMAPS2-inspired "
              "framework (Hwang et al., 2020 [14]). For each SE event five flanking regions are "
              "extracted from GRCh38 (samtools faidx): upstream exon (50 nt), upstream intron "
              "(200 nt), skipped exon (full sequence), downstream intron (200 nt), and downstream "
              "exon (50 nt). Minus-strand events are reverse-complemented before scanning.", "body"),
            p("Seventeen consensus motifs for ten hnRNP proteins (hnRNP A1/A2, C, D, E1, F/H, "
              "I/PTB, K, L, M, U) are matched using IUPAC-degenerate pattern search derived from "
              "CISBP-RNA (Ray et al., 2013 [17]) and Martinez-Contreras et al. (2006). "
              "For each motif-region pair, the hit rate (fraction of events with ≥ 1 match) is "
              "compared between the significant and background groups using a two-proportion z-test "
              "(pooled proportion). Bonferroni correction (n = 5 regions × 17 motifs = 85 tests) "
              "is applied; associations with p<sub>adj</sub> &lt; 0.05 are reported as significant. "
              "This differs from rMAPS2, which uses a Wilcoxon rank-sum test on sliding-window "
              "densities; our approach tests binary hit rates across genomic sub-regions.", "body"),
            p("<b>Summary — SpliceAnalyzer vs. rMAPS2:</b> rMAPS2 characterises positional RBP "
              "binding preferences through nucleotide-resolution sliding-window density plots and "
              "rank-based non-parametric statistics, making it well-suited for visualising where "
              "along a splicing window a motif is enriched. SpliceAnalyzer instead adopts a "
              "region-centric binary enrichment model: each of the five predefined genomic "
              "sub-regions is treated as a unit, hit rates (fraction of events containing ≥ 1 "
              "motif match) are compared between the significant and background event sets via a "
              "two-proportion z-test, and family-wise error control is applied with Bonferroni "
              "correction across all motif–region pairs. This design trades positional resolution "
              "for statistical clarity and direct interpretability in the context of discrete "
              "regulatory zones (exonic body, proximal/distal intronic flanks), providing a "
              "complementary, region-level view of hnRNP motif associations.", "body"),
            p("<b>9. Pathway Enrichment (Enrichr)</b>", "h3"),
            p("Unique HGNC gene symbols derived from significant splicing events are submitted to "
              "the Enrichr REST API (Ma'ayan Lab; Chen et al., 2013 [15]; Kuleshov et al., 2016 "
              "[16]) via a POST request to <i>/addList</i>. Enrichment is retrieved for five "
              "curated gene-set libraries: KEGG 2021 Human, GO Biological Process 2023, GO "
              "Molecular Function 2023, Reactome 2022, and WikiPathways 2023 Human.", "body"),
            p("For each term the Enrichr combined score is defined as: "
              "CS = |z| × log(p), where z is the deviation from a random background (computed "
              "by Enrichr using a random gene-list model) and p is the Fisher's exact test "
              "p-value. FDR-adjusted p-values use Benjamini-Hochberg correction applied "
              "internally by Enrichr. The top 10 terms per library by adjusted p-value are "
              "retained and displayed in this report.", "body"),
        ]
    story.append(sp())

    # ── Appendix B — References ──────────────────────────────────────────────
    story += [
        p("Appendix B — Bibliographic References", "h2"),
        hr(),
        p("[1] Shen S et al. <i>rMATS: robust and flexible detection of differential "
          "alternative splicing from replicate RNA-Seq data.</i> PNAS. 2014;111(51):E5593-E5601.", "body"),
        p("[2] Schneider TD, Stephens RM. <i>Sequence logos: a new way to display "
          "consensus sequences.</i> Nucleic Acids Res. 1990;18(20):6097-6100.", "body"),
        p("[3] Crooks GE, Hon G, Chandonia JM, Brenner SE. <i>WebLogo: a sequence logo "
          "generator.</i> Genome Research. 2004;14(6):1188-1190.", "body"),
        p("[4] Schneider TD, Stormo GD, Gold L, Ehrenfeucht A. <i>Information content "
          "of binding sites on nucleotide sequences.</i> J Mol Biol. 1986;188(3):415-431.", "body"),
        p("[5] Burge C, Karlin S. <i>Prediction of complete gene structures in human "
          "genomic DNA.</i> J Mol Biol. 1997;268(1):78-94.", "body"),
        p("[6] Shapiro MB, Senapathy P. <i>RNA splice junctions of different classes "
          "of eukaryotes: sequence statistics and functional implications in gene "
          "expression.</i> Nucleic Acids Res. 1987;15(17):7155-7174.", "body"),
        p("[7] Morales J et al. <i>A joint NCBI and EMBL-EBI transcript set for "
          "clinical genomics and research.</i> Nature. 2022;604:310-315.", "body"),
        p("[8] Cunningham F et al. <i>Ensembl 2022.</i> Nucleic Acids Res. "
          "2022;50(D1):D988-D995.", "body"),
        p("[9] Gene Ontology Consortium. <i>The Gene Ontology resource: enriching a "
          "GOld mine.</i> Nucleic Acids Res. 2021;49(D1):D325-D334.", "body"),
        p("[10] Szklarczyk D et al. <i>The STRING database in 2023: protein–protein "
          "association networks with increased coverage.</i> Nucleic Acids Res. "
          "2023;51(D1):D638-D646.", "body"),
        p("[11] Coolidge CJ, Seely RJ, Patton JG. <i>Functional analysis of the "
          "polypyrimidine tract in pre-mRNA splicing.</i> Nucleic Acids Res. "
          "1997;25(4):888-896.", "body"),
        p("[12] Padgett RA, Grabowski PJ, Konarska MM, Seiler SR, Sharp PA. "
          "<i>Splicing of messenger RNA precursors.</i> Annu Rev Biochem. "
          "1986;55:1119-1150.", "body"),
        p("[13] Phipson B, Smyth GK. <i>Permutation P-values should never be zero: "
          "calculating exact P-values when permutations are randomly drawn.</i> "
          "Stat Appl Genet Mol Biol. 2010;9(1):Article 39.", "body"),
        p("[14] Hwang JY, Jung S, Kook TL, Rouchka EC, Bok J, Park JW. "
          "<i>rMAPS2: An update of the RNA map analysis and plotting server for "
          "alternative splicing regulation.</i> Nucleic Acids Res. 2020;48(W1):W300-W306.", "body"),
        p("[15] Chen EY, Tan CM, Kou Y, Duan Q, Wang Z, Meirelles GV, Clark NR, "
          "Ma'ayan A. <i>Enrichr: interactive and collaborative HTML5 gene list "
          "enrichment analysis tool.</i> BMC Bioinformatics. 2013;14:128.", "body"),
        p("[16] Kuleshov MV, Jones MR, Rouillard AD, Fernandez NF, Duan Q, Wang Z, "
          "Koplev S, Jenkins SL, Jagodnik KM, Lachmann A, McDermott MG, Bhatt DL, "
          "Eisenberg D, Ma'ayan A. <i>Enrichr: a comprehensive gene set enrichment "
          "analysis web server 2016 update.</i> Nucleic Acids Res. 2016;44(W1):W90-W97.", "body"),
        p("[17] Ray D, Kazan H, Cook KB, Weirauch MT, Najafabadi HS, Li X et al. "
          "<i>A compendium of RNA-binding motifs for decoding gene regulation.</i> "
          "Nature. 2013;499(7457):172-177.", "body"),
        sp(),
    ]

    # ── Appendix C — Statistical Methods ────────────────────────────────────
    story += [
        p("Appendix C — Statistical Methods", "h2"),
        hr(),
        p("<b>C.1 Splicing Event Statistics (rMATS)</b>", "h3"),
        p("rMATS computes for each event:", "body"),
        p("• <b>delta-PSI</b>: dPSI = PSI<sub>sample1</sub> - PSI<sub>sample2</sub>, "
          "where PSI is the percent spliced in. Range: [-1, +1].", "body"),
        p("• <b>p-value</b>: likelihood-ratio test comparing a model with ΔΨ ≠ 0 "
          "against a null model (ΔΨ = 0), using a multivariate uniform prior "
          "on the individual sample PSI values.", "body"),
        p("• <b>FDR</b>: Benjamini-Hochberg correction across all events.", "body"),
        p("<b>C.2 Sequence Logos</b>", "h3"),
        p("Logos are rendered in <b>frequency mode</b>: every column fills the full "
          "logo height and the height of each letter at position i is:", "body"),
        p("&nbsp;&nbsp;&nbsp;height(b,i) = f(b,i) × H<sub>logo</sub>", "code"),
        p("where f(b,i) is the raw nucleotide frequency of base b at position i "
          "and H<sub>logo</sub> is the fixed column height. No information-content "
          "(bits) scaling or small-sample correction is applied. This makes every "
          "column directly comparable and matches the frequency view in the web "
          "application. Base colours: A = green, C = blue, G = orange, T = red.", "body"),
        p("<b>C.3 PPT Score</b>", "h3"),
        p("The polypyrimidine tract (PPT) score is the fraction of pyrimidine "
          "nucleotides (C, T) in the ~47 nt window upstream of the acceptor site. "
          "The branch point is detected by matching the YNYURAY motif within the "
          "PPT window (Coolidge et al., 1997).", "body"),
    ]
    if is_deep:
        story += [
            p("<b>C.4 Deep Analysis Statistical Tests</b>", "h3"),
            p("Events are split into significant and non-significant groups. "
              "The following two-tailed tests compare splice features:", "body"),
            p("• <b>Welch's t-test</b>: for continuous features (mean delta-PSI, exon size, "
              "PPT score). Uses Welch-Satterthwaite approximation for degrees of freedom:", "body"),
            p("&nbsp;&nbsp;&nbsp;df = (s<sub>1</sub><super>2</super>/n<sub>1</sub> + s<sub>2</sub><super>2</super>/n<sub>2</sub>)<super>2</super> "
              "/ [(s<sub>1</sub><super>2</super>/n<sub>1</sub>)<super>2</super>/(n<sub>1</sub>-1) "
              "+ (s<sub>2</sub><super>2</super>/n<sub>2</sub>)<super>2</super>/(n<sub>2</sub>-1)]", "code"),
            p("• <b>Two-proportion z-test</b>: for proportions (canonical GT, canonical AG, "
              "upstream GT, downstream AG, in-frame %, branch-point detection):", "body"),
            p("&nbsp;&nbsp;&nbsp;z = (p<sub>1</sub> - p<sub>2</sub>) "
              "/ sqrt[p(1-p)(1/n<sub>1</sub> + 1/n<sub>2</sub>)]", "code"),
            p("where p is the pooled proportion across both groups.", "body"),
            p("All p-values are two-tailed. The regularised incomplete beta function "
              "is computed via Lentz's continued fraction algorithm for the t-distribution CDF.", "body"),
            p("<b>C.5 Permutation Test</b>", "h3"),
            p("For each significant SE event, sample-label permutation generates a null ΔΨ "
              "distribution.  The empirical p-value is: p = (r + 1) / (K + 1), where r is "
              "the number of permuted |ΔΨ| ≥ observed |ΔΨ| and K is the number of iterations.  "
              "The +1 correction avoids p = 0 (Phipson &amp; Smyth, 2010 [13]).  "
              "The test is run at 50, 100, 250 and 500 iterations to demonstrate convergence.", "body"),
            p("<b>C.6 hnRNP Motif Enrichment — Two-Proportion z-Test</b>", "h3"),
            p("For each motif m in region r, let x<sub>1</sub> / n<sub>1</sub> be the hit rate "
              "in the significant group and x<sub>2</sub> / n<sub>2</sub> in the background. "
              "The pooled proportion is p̂ = (x<sub>1</sub> + x<sub>2</sub>) / "
              "(n<sub>1</sub> + n<sub>2</sub>). The test statistic is:", "body"),
            p("&nbsp;&nbsp;&nbsp;z = (p̂<sub>1</sub> - p̂<sub>2</sub>) / "
              "sqrt[ p̂(1 - p̂)(1/n<sub>1</sub> + 1/n<sub>2</sub>) ]", "code"),
            p("Two-tailed p-values are computed from the standard normal CDF. "
              "Bonferroni correction multiplies each p-value by the number of tests "
              "(85 = 5 regions × 17 motifs). Groups with fewer than 5 events are skipped.", "body"),
            p("<b>C.7 Enrichr Combined Score</b>", "h3"),
            p("The Enrichr combined score (Chen et al., 2013 [15]) is defined as:", "body"),
            p("&nbsp;&nbsp;&nbsp;CS = |z| × log(p)", "code"),
            p("where z is the z-score computed by Enrichr against a random background model "
              "(draws from the full human gene set) and p is the Fisher's exact test p-value "
              "for overlap between the submitted gene list and the gene set. "
              "A higher CS indicates stronger enrichment signal beyond background expectation. "
              "BH-FDR adjusted p-values are applied within each library.", "body"),
        ]
    story.append(sp())

    doc.build(story)
    return buf.getvalue()


@router.get("/{analysis_id}/pdf")
async def export_analysis_pdf(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Generate a PDF analysis report for *analysis_id* (all events)."""

    analysis, group1_label, group2_label = await _get_analysis_with_groups(db, analysis_id)
    events, features = await _load_events_and_features(db, analysis_id)

    pdf_bytes = await asyncio.to_thread(_build_pdf, analysis, events, features, group1_label, group2_label)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_{analysis_id}.pdf"'
        },
    )


@router.get("/{analysis_id}/deep-analysis/{deep_analysis_id}/pdf")
async def export_deep_analysis_pdf(
    analysis_id: uuid.UUID,
    deep_analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Generate a PDF report scoped to a deep analysis (filtered events + comparison)."""
    from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent
    from app.routers.deep_analyses import _compute_group_stats, _compute_stat_tests

    analysis, group1_label, group2_label = await _get_analysis_with_groups(db, analysis_id)

    # Fetch deep analysis record
    deep = (await db.execute(
        select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
    )).scalar_one_or_none()
    if not deep:
        raise HTTPException(status_code=404, detail="Deep analysis not found")

    # Fetch all events tagged in this deep analysis
    q = (
        select(SplicingEvent, DeepAnalysisEvent.is_significant)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(DeepAnalysisEvent.deep_analysis_id == deep_analysis_id)
    )
    rows = (await db.execute(q)).all()
    events = [ev for ev, _ in rows]
    sig_map = {ev.id: is_sig for ev, is_sig in rows}

    # Fetch splice features for SE events (subquery avoids parameter limit)
    se_subq = (
        select(SplicingEvent.id)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    features: dict[uuid.UUID, EventSpliceFeature] = {}
    feat_result = await db.execute(
        select(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(se_subq))
    )
    for feat in feat_result.scalars().all():
        features[feat.event_id] = feat

    # Compute pattern comparison (reusing deep_analyses helpers)
    se_event_ids = [e.id for e in events if e.event_type == "SE"]
    sig_feats = [features[eid] for eid in se_event_ids if sig_map.get(eid) and eid in features]
    nonsig_feats = [features[eid] for eid in se_event_ids if not sig_map.get(eid) and eid in features]
    sig_events = [e for e in events if e.event_type == "SE" and sig_map.get(e.id)]
    nonsig_events = [e for e in events if e.event_type == "SE" and not sig_map.get(e.id)]

    stat_tests = _compute_stat_tests(sig_events, sig_feats, nonsig_events, nonsig_feats)

    comparison = {
        "significant": _compute_group_stats(sig_events, sig_feats).model_dump(),
        "not_significant": _compute_group_stats(nonsig_events, nonsig_feats).model_dump(),
        "statistical_tests": [
            {"feature": t.feature, "test_name": t.test_name,
             "statistic": t.statistic, "p_value": t.p_value, "significant": t.significant}
            for t in stat_tests
        ],
    }

    # ── hnRNP motif enrichment ────────────────────────────────────────────
    async def _compute_hnrnp() -> dict | None:
        """Run hnRNP motif enrichment on SE events; returns plain dict or None."""
        try:
            from app.services.hnrnp_motifs import SERegions, define_se_regions, compare_groups, scan_group
            from app.services.sequence import extract_regions_batch, reverse_complement
            from app.config import settings

            se_sig = [e for e in sig_events if e.event_type == "SE"]
            se_bg = [e for e in nonsig_events if e.event_type == "SE"]

            def _build_regions(evs: list) -> list:
                if not evs:
                    return []
                all_bed: list = []
                strands: list[str] = []
                for ev in evs:
                    if not ev.chr or ev.exon_start is None or ev.exon_end is None:
                        for _ in range(5):
                            all_bed.append(("", 0, 0))
                        strands.append(ev.strand or "+")
                        continue
                    bed = define_se_regions(
                        ev.chr, ev.strand or "+",
                        ev.exon_start, ev.exon_end,
                        ev.upstream_es, ev.upstream_ee,
                        ev.downstream_es, ev.downstream_ee,
                    )
                    all_bed.extend(bed)
                    strands.append(ev.strand or "+")
                seqs = extract_regions_batch(all_bed, settings.GRCH38_FASTA)
                result: list = []
                for idx, strand in enumerate(strands):
                    s = seqs[idx * 5: idx * 5 + 5]
                    if strand == "-":
                        s = [reverse_complement(x) if x else "" for x in s]
                    result.append(SERegions(
                        upstream_exon=s[0], upstream_intron=s[1],
                        skipped_exon=s[2], downstream_intron=s[3], downstream_exon=s[4],
                    ))
                return result

            sig_regions, bg_regions = await asyncio.gather(
                asyncio.to_thread(_build_regions, se_sig),
                asyncio.to_thread(_build_regions, se_bg),
            )
            sig_scan, bg_scan = await asyncio.gather(
                asyncio.to_thread(scan_group, sig_regions),
                asyncio.to_thread(scan_group, bg_regions),
            )
            enrichment = await asyncio.to_thread(compare_groups, sig_scan, bg_scan)
            return {
                "n_sig_events": len(se_sig),
                "n_bg_events": len(se_bg),
                "results": [
                    {
                        "motif_name": r.motif_name,
                        "protein": r.protein,
                        "region": r.region,
                        "sig_hit_count": r.sig_hit_count,
                        "sig_total": r.sig_total,
                        "bg_hit_count": r.bg_hit_count,
                        "bg_total": r.bg_total,
                        "sig_density": r.sig_density,
                        "bg_density": r.bg_density,
                        "z_stat": r.z_stat,
                        "p_value": r.p_value,
                        "p_adjusted": r.p_adjusted,
                        "significant": r.significant,
                    }
                    for r in enrichment
                ],
            }
        except Exception as exc:
            logger.warning("hnRNP computation skipped in PDF (non-fatal): %s", exc)
            return None

    # ── Enrichr pathway enrichment ────────────────────────────────────────
    async def _compute_enrichr() -> dict | None:
        """Run Enrichr on gene symbols from significant events; returns plain dict or None."""
        try:
            from app.services.enrichr import run_enrichment

            q_genes = (
                select(SplicingEvent.gene_symbol)
                .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
                .where(
                    DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
                    DeepAnalysisEvent.is_significant.is_(True),
                    SplicingEvent.gene_symbol.isnot(None),
                )
                .distinct()
            )
            gene_rows = (await db.execute(q_genes)).scalars().all()
            gene_symbols = [s for s in gene_rows if s and s.strip()]
            if not gene_symbols:
                return None
            result = await asyncio.to_thread(run_enrichment, gene_symbols)
            if result.error and not result.terms:
                return None
            return {
                "n_genes_submitted": result.n_genes_submitted,
                "terms": [
                    {
                        "library": t.library,
                        "rank": t.rank,
                        "term": t.term,
                        "p_value": t.p_value,
                        "adjusted_p_value": t.adjusted_p_value,
                        "z_score": t.z_score,
                        "combined_score": t.combined_score,
                        "overlap": t.overlap,
                        "genes": t.genes,
                    }
                    for t in result.terms
                ],
            }
        except Exception as exc:
            logger.warning("Enrichr computation skipped in PDF (non-fatal): %s", exc)
            return None

    # ── Permutation test (single run at 500 iterations) ─────────────────
    from app.services.permutation import run_permutation

    sig_features_list = [features.get(e.id) for e in sig_events]

    async def _compute_permutation() -> list[dict]:
        if not sig_events:
            return []
        perm_res = await asyncio.to_thread(
            run_permutation,
            sig_events,
            sig_features_list,
            n_iterations=500,
            only_se=True,
            seed=42,
        )
        return [{
            "iterations": 500,
            "n_tested": perm_res.n_events_tested,
            "pct_p05": perm_res.pct_p05,
            "pct_p01": perm_res.pct_p01,
        }]

    # Run all three analyses concurrently
    permutation_table, hnrnp_data, enrichr_data = await asyncio.gather(
        _compute_permutation(),
        _compute_hnrnp(),
        _compute_enrichr(),
    )

    pdf_bytes = await asyncio.to_thread(
        _build_pdf, analysis, events, features, group1_label, group2_label,
        deep_analysis=deep, comparison=comparison,
        sig_map=sig_map, permutation_table=permutation_table,
        hnrnp_data=hnrnp_data, enrichr_data=enrichr_data,
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_deep_{deep_analysis_id}.pdf"'
        },
    )
