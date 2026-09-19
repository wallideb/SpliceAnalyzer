from __future__ import annotations

import asyncio
import logging
import os
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

from sqlalchemy import func as sa_func

from app.config import settings as _settings
from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.models.splice import EventSpliceFeature
from app.services.splice_features import (
    compute_pwm as _compute_pwm,
    ppt_t_content as _ppt_t_content,
    ppt_c_content as _ppt_c_content,
)
from app.services.panelapp import get_panels_for_gene
from app.services.gene_ontology import get_go_terms
from app.services.stringdb import get_interaction

# ── Column group identifiers ──────────────────────────────────────────────────
ColumnGroup = Literal["core", "panelapp", "go", "stringdb"]
ALL_GROUPS: tuple[ColumnGroup, ...] = ("core", "panelapp", "go", "stringdb")

router = APIRouter(prefix="/export", tags=["export"])

# Limit concurrent outbound HTTP requests to external APIs (PanelApp, GO, STRING-DB)
# to avoid socket/connection-pool exhaustion on large exports (200+ genes).
_EXT_API_SEMAPHORE = asyncio.Semaphore(20)


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


async def _assert_splice_features_ready(
    db: AsyncSession, analysis_id: uuid.UUID
) -> None:
    """Raise 409 Conflict if splice-feature computation is still in progress.

    Reads ``analyses.compute_status`` (persisted by the splice router).  If
    the task has finished (even with partial failures), the check passes so
    users aren't blocked from exporting what was computed.
    """
    from app.routers.splice import get_compute_status

    n_se = (await db.execute(
        select(sa_func.count(SplicingEvent.id)).where(
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )).scalar() or 0

    if n_se == 0:
        return

    n_computed = (await db.execute(
        select(sa_func.count(EventSpliceFeature.id)).where(
            EventSpliceFeature.event_id.in_(
                select(SplicingEvent.id).where(
                    SplicingEvent.analysis_id == analysis_id,
                    SplicingEvent.event_type == "SE",
                )
            )
        )
    )).scalar() or 0

    # Allow export if the background task has finished (even partially)
    task_running = (await get_compute_status(db, analysis_id)) == "running"
    if n_computed < n_se and task_running:
        pct = round(n_computed / n_se * 100, 1)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Splice feature computation is still in progress "
                f"({n_computed}/{n_se} events, {pct}%). "
                f"Please wait until computation completes before generating the PDF."
            ),
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
        # Use asyncio.wait with a global cap so a slow PanelApp doesn't stall
        # the entire export. Tasks that don't finish within 25 s are cancelled
        # and contribute empty results (same as a normal "no panel found").
        _pa_tasks = [asyncio.ensure_future(_throttled(get_panels_for_gene(sym))) for sym in unique_symbols]
        _done, _pending = await asyncio.wait(_pa_tasks, timeout=25.0)
        for t in _pending:
            t.cancel()
        pa_results: list = []
        for task in _pa_tasks:
            if task in _done:
                try:
                    pa_results.append(task.result())
                except Exception:
                    pa_results.append([])
            else:
                pa_results.append([])
        if _pending:
            logger.warning("PanelApp: %d gene(s) timed out (global 25 s cap), returning empty results", len(_pending))
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
            # The STRING pair endpoint (get_interaction) is queried once per
            # (gene, mutated-gene candidate) pair after deduplication of
            # unordered, case-insensitive pairs, under the shared concurrency cap.
            _seen_pairs: set[frozenset[str]] = set()
            pairs: list[tuple[str, str]] = []
            for sym in unique_symbols:
                for mut in mutated_genes_list:
                    if sym.upper() == mut.upper():
                        continue
                    key = frozenset((sym.upper(), mut.upper()))
                    if key in _seen_pairs:
                        continue
                    _seen_pairs.add(key)
                    pairs.append((sym, mut))
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
    ws_sum.append(["p-value maximum", deep.pvalue_threshold if deep.pvalue_threshold is not None else "not applied"])
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
from datetime import date as _date

from reportlab.lib import colors as _colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4 as _A4, landscape as _landscape
from reportlab.lib.styles import getSampleStyleSheet as _getStyles, ParagraphStyle
from reportlab.lib.units import cm as _cm
from reportlab.platypus import (
    BaseDocTemplate, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, NextPageTemplate, PageTemplate, Frame,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group, PolyLine
from reportlab.graphics import renderSVG as _renderSVG
from reportlab.pdfbase import pdfmetrics as _pdfmetrics
_W, _ = _A4
_MARGIN = 2 * _cm

# SeqLogo rendering constants — precomputed once at import time so the
# per-column / per-base inner loop never recreates them.
_LOGO_BASE_COLORS: dict[str, str] = {
    "A": "#22c55e", "C": "#3b82f6", "G": "#f97316", "T": "#ef4444",
}
_LOGO_BASE_COLOR_OBJS: dict[str, object] = {
    b: _colors.HexColor(h) for b, h in _LOGO_BASE_COLORS.items()
}
_LOGO_REF_FS: float = 100.0
_LOGO_CAP_H:  float = _LOGO_REF_FS * 0.718  # Helvetica-Bold cap height ≈ 71.8 %
_LOGO_PAD:    int   = 1                       # horizontal padding per side (pts)
# Precomputed per-base natural glyph widths at _LOGO_REF_FS / Helvetica-Bold.
_LOGO_BASE_NAT_W: dict[str, float] = {
    b: _pdfmetrics.stringWidth(b, "Helvetica-Bold", _LOGO_REF_FS)
    for b in "ACGT"
}


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
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"],
            fontSize=10, spaceBefore=8, spaceAfter=4,
            textColor=_colors.HexColor("#475569"),
            keepWithNext=True,
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
        # Table cell styles — used by _make_tbl() for proper word-wrapping
        "tbl_h": ParagraphStyle(
            "TblH", parent=base["Normal"],
            fontSize=8, leading=10, spaceAfter=0, spaceBefore=0,
            fontName="Helvetica-Bold", textColor=_colors.white,
        ),
        "tbl_c": ParagraphStyle(
            "TblC", parent=base["Normal"],
            fontSize=7.5, leading=10, spaceAfter=0, spaceBefore=0,
            fontName="Helvetica", textColor=_colors.HexColor("#0f172a"),
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


def _make_tbl(rows, col_widths, S, style_fn=None):
    """Build a Table with all string cells wrapped in Paragraphs for word-wrapping.

    Row 0 is treated as the header (white bold style); other rows use the data
    cell style.  Non-string cells (e.g. existing Paragraphs, Drawings) are
    passed through unchanged.
    """
    wrapped = []
    for ri, row in enumerate(rows):
        wr = []
        for cell in row:
            if isinstance(cell, str):
                wr.append(Paragraph(cell, S["tbl_h"] if ri == 0 else S["tbl_c"]))
            else:
                wr.append(cell)
        wrapped.append(wr)
    tbl = Table(wrapped, colWidths=col_widths)
    tbl.setStyle((style_fn or _tbl_style)())
    return tbl


# ---------------------------------------------------------------------------
# hnRNP heatmap builder (protein × region, with regulatory effect frames)
# ---------------------------------------------------------------------------

# Seven regions per SE event, in transcript order (rMAPS2 design: 250-nt
# windows after each 5'SS and before each 3'SS, plus the exonic flanks and the
# full skipped exon).  Must match hnrnp_motifs.REGION_NAMES.
_HEATMAP_REGION_ORDER = [
    "upstream_exon",
    "upstream_intron_5ss",
    "upstream_intron_3ss",
    "skipped_exon",
    "downstream_intron_5ss",
    "downstream_intron_3ss",
    "downstream_exon",
]
_HEATMAP_REGION_LABELS = {
    "upstream_exon": "Upstream\nexon",
    "upstream_intron_5ss": "Upstream\nintron\n(5'SS side)",
    "upstream_intron_3ss": "Upstream\nintron\n(3'SS side)",
    "skipped_exon": "Skipped\nexon",
    "downstream_intron_5ss": "Downstream\nintron\n(5'SS side)",
    "downstream_intron_3ss": "Downstream\nintron\n(3'SS side)",
    "downstream_exon": "Downstream\nexon",
}
# Single-line labels for tables
_REGION_TABLE_LABELS = {
    "upstream_exon": "Upstream exon",
    "upstream_intron_5ss": "Upstream intron (5'SS)",
    "upstream_intron_3ss": "Upstream intron (3'SS)",
    "skipped_exon": "Skipped exon",
    "downstream_intron_5ss": "Downstream intron (5'SS)",
    "downstream_intron_3ss": "Downstream intron (3'SS)",
    "downstream_exon": "Downstream exon",
}


def _heatmap_region_order(hnrnp_data: dict) -> list[str]:
    """Region columns for the heatmap: the order reported by the service when
    available (``regions`` key), otherwise the module default."""
    regs = hnrnp_data.get("regions")
    if isinstance(regs, list) and regs:
        return [str(r) for r in regs]
    return list(_HEATMAP_REGION_ORDER)


def _build_hnrnp_heatmap(hnrnp_data: dict) -> Drawing | None:
    """Build a vector heatmap Drawing: protein families × genomic regions.

    For each protein × region cell, the most significant motif (presence
    test, BH-adjusted) is shown.  Cell background encodes enrichment/depletion
    (red/blue/grey).  An orange (silencer) or green (enhancer) border frame
    indicates the established regulatory effect when available.  Seven
    region columns (7 × 55 pt + 92 pt label column = 477 pt) fit the
    portrait text frame.
    """
    results = hnrnp_data.get("results", [])
    if not results:
        return None

    proteins = list(dict.fromkeys(r.get("protein", "") for r in results))
    if not proteins:
        return None

    region_order = _heatmap_region_order(hnrnp_data)

    # Build matrix: protein → region → best motif (lowest p_adjusted)
    matrix: dict[str, dict[str, dict | None]] = {}
    for prot in proteins:
        matrix[prot] = {}
        for reg in region_order:
            candidates = [r for r in results if r.get("protein") == prot and r.get("region") == reg]
            best = None
            for c in candidates:
                p_adj = c.get("p_adjusted")
                if p_adj is None:
                    continue
                if best is None or p_adj < (best.get("p_adjusted") or 1.0):
                    best = c
            matrix[prot][reg] = best

    # Drawing dimensions (7 columns must fit the 482 pt portrait frame)
    cell_w = 55
    cell_h = 28
    label_w = 92   # protein name column width
    header_h = 36  # three header lines
    n_rows = len(proteins)
    n_cols = len(region_order)
    total_w = label_w + n_cols * cell_w
    total_h = header_h + n_rows * cell_h + 12  # +12 for top margin

    d = Drawing(total_w, total_h)

    # Colours
    clr_enriched = _colors.HexColor("#fecaca")   # red-200
    clr_depleted = _colors.HexColor("#bfdbfe")   # blue-200
    clr_ns       = _colors.HexColor("#f1f5f9")   # slate-100
    clr_silencer = _colors.HexColor("#ea580c")   # orange-600
    clr_enhancer = _colors.HexColor("#059669")   # emerald-600
    clr_grid     = _colors.HexColor("#e2e8f0")   # slate-200
    clr_text     = _colors.HexColor("#0f172a")   # slate-900
    clr_muted    = _colors.HexColor("#94a3b8")   # slate-400
    clr_header   = _colors.HexColor("#475569")   # slate-600

    # Column headers
    for ci, reg in enumerate(region_order):
        x = label_w + ci * cell_w
        y = total_h - header_h
        label = _HEATMAP_REGION_LABELS.get(reg, reg.replace("_", "\n"))
        lines = label.split("\n")
        for li, line in enumerate(lines):
            d.add(String(
                x + cell_w / 2, y + (len(lines) - 1 - li) * 8 + 2,
                line, fontSize=6, fontName="Helvetica-Bold",
                fillColor=clr_header, textAnchor="middle",
            ))

    # Rows
    for ri, prot in enumerate(proteins):
        y = total_h - header_h - (ri + 1) * cell_h

        # Protein label
        d.add(String(
            label_w - 4, y + cell_h / 2 - 3,
            prot, fontSize=6.5, fontName="Helvetica-Bold",
            fillColor=clr_text, textAnchor="end",
        ))

        for ci, reg in enumerate(region_order):
            x = label_w + ci * cell_w
            item = matrix[prot][reg]

            if item is None or item.get("p_adjusted") is None:
                # Empty cell
                d.add(Rect(x, y, cell_w, cell_h, fillColor=clr_ns,
                           strokeColor=clr_grid, strokeWidth=0.3))
                d.add(String(x + cell_w / 2, y + cell_h / 2 - 3, "—",
                             fontSize=7, fillColor=clr_muted, textAnchor="middle"))
                continue

            p_adj = item["p_adjusted"]
            sig = p_adj < 0.05
            enriched = (item.get("sig_density", 0) or 0) > (item.get("bg_density", 0) or 0)

            # Cell background
            if sig and enriched:
                bg = clr_enriched
            elif sig and not enriched:
                bg = clr_depleted
            else:
                bg = clr_ns

            d.add(Rect(x, y, cell_w, cell_h, fillColor=bg,
                        strokeColor=clr_grid, strokeWidth=0.3))

            # Regulatory effect border frame (thicker inset border)
            effect = item.get("regulatory_effect")
            if effect:
                frame_clr = clr_silencer if effect in ("ESS", "ISS") else clr_enhancer
                inset = 1.5
                d.add(Rect(
                    x + inset, y + inset,
                    cell_w - 2 * inset, cell_h - 2 * inset,
                    fillColor=None, strokeColor=frame_clr, strokeWidth=1.5,
                ))

            # Motif name text
            motif_name = item.get("motif_name", "")
            text_color = clr_text if sig else clr_muted
            suffix = "*" if sig else ""
            d.add(String(
                x + cell_w / 2, y + cell_h / 2 + (2 if effect else -1),
                motif_name + suffix,
                fontSize=6.5, fontName="Courier-Bold",
                fillColor=text_color, textAnchor="middle",
            ))

            # Effect label below motif name
            if effect:
                eff_color = clr_silencer if effect in ("ESS", "ISS") else clr_enhancer
                d.add(String(
                    x + cell_w / 2, y + 3,
                    effect,
                    fontSize=5.5, fontName="Helvetica-Bold",
                    fillColor=eff_color, textAnchor="middle",
                ))

    return d


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


def _fig_frame_breakdown(n_if: int, n_fs: int, n_nc: int, n_unknown: int = 0) -> Drawing | None:
    """Horizontal stacked bar showing reading-frame class proportions.

    Percentages are computed over events with a KNOWN frame class
    (n_if + n_fs + n_nc); ``n_unknown`` (no MANE annotation) is only
    reported beside the bar, never used as part of the denominator.
    """
    n_known = n_if + n_fs + n_nc
    if n_known == 0:
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
        seg_w = (count / n_known) * bar_w
        d.add(Rect(x, BAR_Y, seg_w, BAR_H,
                    fillColor=_colors.HexColor(color), strokeColor=None))
        # Label inside if wide enough
        pct = count / n_known * 100
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
        d.add(String(lx + 10, 2, f"{label}: {count} ({count / n_known * 100:.1f}%)",
                      fontSize=5.5, fontName="Helvetica", fillColor=_colors.HexColor("#475569")))
        lx += 110

    # Unknown frames (excluded from the percentages) — right-aligned note
    d.add(String(W - MARGIN_L, 2,
                  f"{n_unknown} unknown (not shown)  ·  n = {n_known} known",
                  fontSize=5.5, fontName="Helvetica-Oblique",
                  fillColor=_colors.HexColor("#64748b"), textAnchor="end"))

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
        # Same alignment as the API routers: donors are the FIRST 9 nt
        # (3 exon + 6 intron), acceptors the LAST 23 nt (20 intron + 3 exon),
        # so a longer-than-expected window is trimmed on the correct side.
        sequences = []
        expected_len = 9 if site == "donor" else 23
        for f in features_dict.values():
            seq = f.donor_seq if site == "donor" else f.acceptor_seq
            if seq and len(seq) >= expected_len:
                sequences.append(
                    seq[:expected_len].upper() if site == "donor" else seq[-expected_len:].upper()
                )
        if len(sequences) < 3:
            return None
        pwm = _compute_pwm(sequences)

    seq_len = len(pwm)
    if seq_len == 0:
        return None

    COL_W  = min(22, int((max_width - 16) / seq_len))
    LOGO_H = 80
    MARGIN_L, MARGIN_B, MARGIN_T = 8, 24, 8
    W = min(max_width, MARGIN_L + seq_len * COL_W + 8)
    H = MARGIN_T + LOGO_H + MARGIN_B
    # Per-call derived constants (COL_W is now fixed for this logo instance)
    avail_w = COL_W - 2 * _LOGO_PAD

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

        # Frequency mode: every column fills LOGO_H; letter height ∝ frequency.
        # Each letter is stretched to fill its allocated width × height slot,
        # matching the web app's SVG preserveAspectRatio="none" approach.
        # Module-level constants (_LOGO_*) are used to avoid per-iteration recomputation.
        sorted_bases = sorted(freqs.items(), key=lambda kv: kv[1])
        cur_y = MARGIN_B
        for base, freq in sorted_bases:
            if freq <= 0:
                continue
            h = freq * LOGO_H
            if h < 0.5:
                cur_y += h
                continue
            sx = avail_w / max(_LOGO_BASE_NAT_W[base], 0.1)
            sy = h / _LOGO_CAP_H
            g = Group(
                String(0, 0, base,
                       fontSize=_LOGO_REF_FS,
                       fontName="Helvetica-Bold",
                       fillColor=_LOGO_BASE_COLOR_OBJS[base],
                       textAnchor="start"),
                transform=(sx, 0, 0, sy, x + _LOGO_PAD, cur_y),
            )
            d.add(g)
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


# ---------------------------------------------------------------------------
# Summary schematic — exon-intron diagram with significance annotations
# ---------------------------------------------------------------------------

def _fig_summary_schematic(
    comparison: dict,
    sig_data: dict,
    nonsig_data: dict,
    *,
    group1_label: str = "Group 1",
) -> Drawing | None:
    """Build a modern vector schematic of the exon-skipping architecture."""
    tests = comparison.get("statistical_tests", [])
    test_map = {t["feature"]: t for t in tests}

    # ── Layout ──
    W = 730
    H = 380

    # Vertical zones (top→bottom in ReportLab coords, 0=bottom):
    #   H-18   title
    #   ~343   "exon skipping" label (above arc)
    #   ~335   arc top
    #   ~315   mean ΔΨ (under arc, above exon)
    #   270    intron labels
    #   EXON_Y exon row (height EXON_H)
    #   ~200   frame badge
    #   ~170   sequence row (single row, all 4)
    #   ~100   PPT / BP area
    EXON_Y = 218
    EXON_H = 38
    MID_Y  = EXON_Y + EXON_H / 2

    # Horizontal — centred, wider spacing
    TOTAL_W = 660
    M_L = (W - TOTAL_W) / 2       # ~35
    FLANK_W = 90
    SKIP_W  = 150
    INTRON_W = 140

    UP_X1 = M_L
    UP_X2 = UP_X1 + FLANK_W
    INT1_X1 = UP_X2
    INT1_X2 = INT1_X1 + INTRON_W
    SK_X1 = INT1_X2
    SK_X2 = SK_X1 + SKIP_W
    INT2_X1 = SK_X2
    INT2_X2 = INT2_X1 + INTRON_W
    DN_X1 = INT2_X2
    DN_X2 = DN_X1 + FLANK_W

    # ── Colours (modern palette matching the web app) ──
    CLR_FLANK   = _colors.HexColor("#64748b")
    CLR_SKIP    = _colors.HexColor("#6366f1")
    CLR_INTRON  = _colors.HexColor("#94a3b8")
    CLR_SIG     = _colors.HexColor("#dc2626")
    CLR_PPT     = _colors.HexColor("#f59e0b")
    CLR_BP      = _colors.HexColor("#16a34a")
    CLR_BG      = _colors.HexColor("#ffffff")
    CLR_BORDER  = _colors.HexColor("#e2e8f0")
    CLR_SEQ_BG  = _colors.HexColor("#f8fafc")
    CLR_GT_BG   = _colors.HexColor("#fef9c3")
    CLR_CARD    = _colors.HexColor("#f1f5f9")
    CLR_TXT     = _colors.HexColor("#334155")
    CLR_TXT2    = _colors.HexColor("#64748b")

    d = Drawing(W, H)

    # ── Background card with subtle border ──
    d.add(Rect(0, 0, W, H, fillColor=CLR_BG, strokeColor=CLR_BORDER, strokeWidth=0.8, rx=6, ry=6))

    # ── Title bar ──
    d.add(Rect(0, H - 30, W, 30, fillColor=_colors.HexColor("#f8fafc"),
               strokeColor=None, rx=6, ry=6))
    # Cover bottom corners of title bar
    d.add(Rect(0, H - 30, W, 10, fillColor=_colors.HexColor("#f8fafc"), strokeColor=None))
    d.add(Line(0, H - 30, W, H - 30, strokeColor=CLR_BORDER, strokeWidth=0.5))
    d.add(String(W / 2, H - 20,
                 f"Skipped-exon splice features — {group1_label}",
                 fontSize=10, fontName="Helvetica-Bold",
                 fillColor=_colors.HexColor("#1e293b"), textAnchor="middle"))

    # ── Helpers ──
    def _star(feature: str) -> bool:
        t = test_map.get(feature)
        return t is not None and t.get("significant", False)

    def _add_star_pval(x: float, y: float, feature: str, *, anchor: str = "middle"):
        t = test_map.get(feature)
        if not t or not t.get("significant"):
            return
        d.add(String(x, y, "★", fontSize=11, fontName="Helvetica-Bold",
                     fillColor=CLR_SIG, textAnchor=anchor))
        pv = t.get("p_value")
        if pv is not None:
            pv_str = f"p={pv:.2e}" if pv < 0.001 else f"p={pv:.3f}"
            d.add(String(x, y - 10, pv_str, fontSize=6, fontName="Helvetica",
                         fillColor=CLR_SIG, textAnchor=anchor))

    # ── Exons (rounded rectangles with shadow effect) ──
    for ex1, ex2, ew, label_top, label_bot, clr, fs in [
        (UP_X1, UP_X2, FLANK_W, "Upstream", "exon", CLR_FLANK, 8),
        (SK_X1, SK_X2, SKIP_W,  "Skipped",  "exon", CLR_SKIP,  9),
        (DN_X1, DN_X2, FLANK_W, "Downstream", "exon", CLR_FLANK, 7.5),
    ]:
        # Subtle shadow
        d.add(Rect(ex1 + 1.5, EXON_Y - 1.5, ew, EXON_H,
                   fillColor=_colors.HexColor("#00000010"), strokeColor=None, rx=5, ry=5))
        d.add(Rect(ex1, EXON_Y, ew, EXON_H,
                   fillColor=clr, strokeColor=None, rx=5, ry=5))
        d.add(String((ex1 + ex2) / 2, EXON_Y + EXON_H / 2 - 5,
                     label_top, fontSize=fs, fontName="Helvetica-Bold",
                     fillColor=_colors.white, textAnchor="middle"))
        d.add(String((ex1 + ex2) / 2, EXON_Y + EXON_H / 2 + 7,
                     label_bot, fontSize=8, fontName="Helvetica-Bold",
                     fillColor=_colors.Color(1, 1, 1, 0.8), textAnchor="middle"))

    # ── Introns (smooth V-shaped lines) ──
    for ix1, ix2 in [(INT1_X1, INT1_X2), (INT2_X1, INT2_X2)]:
        mid_x = (ix1 + ix2) / 2
        notch = 12
        d.add(PolyLine([ix1, MID_Y, mid_x, MID_Y + notch, ix2, MID_Y],
                        strokeColor=CLR_INTRON, strokeWidth=1.8))

    # ── Intron size labels (above intron V) ──
    INTRON_LABEL_Y = EXON_Y + EXON_H + 20
    for ix1, ix2, feat, data_key in [
        (INT1_X1, INT1_X2, "upstream_intron_size", "upstream_intron_size_mean"),
        (INT2_X1, INT2_X2, "downstream_intron_size", "downstream_intron_size_mean"),
    ]:
        mid_x = (ix1 + ix2) / 2
        sz = sig_data.get(data_key)
        label = f"{sz:,.0f} nt" if sz is not None else "? nt"
        d.add(String(mid_x, INTRON_LABEL_Y, label,
                     fontSize=7.5, fontName="Helvetica",
                     fillColor=CLR_TXT, textAnchor="middle"))
        _add_star_pval(mid_x + 30, INTRON_LABEL_Y - 2, feat)

    # ── Skipping arc (dashed, above exons) ──
    arc_base = EXON_Y + EXON_H + 34
    arc_height = 45
    n_pts = 50
    arc_pts: list[float] = []
    for i in range(n_pts + 1):
        t = i / n_pts
        x = UP_X2 + t * (DN_X1 - UP_X2)
        y = arc_base + 4 * arc_height * t * (1 - t)
        arc_pts.extend([x, y])
    d.add(PolyLine(arc_pts, strokeColor=_colors.HexColor("#a78bfa"),
                    strokeWidth=1.6, strokeDashArray=[6, 4]))
    d.add(String((UP_X2 + DN_X1) / 2, arc_base + arc_height + 8,
                 "exon skipping", fontSize=8, fontName="Helvetica-Oblique",
                 fillColor=_colors.HexColor("#7c3aed"), textAnchor="middle"))

    # ── Mean ΔΨ (just under the arc, above skipped exon) ──
    dpsi = sig_data.get("mean_delta_psi")
    if dpsi is not None:
        dpsi_y = arc_base + arc_height - 20
        dpsi_str = f"Mean ΔΨ: {dpsi:+.3f}"
        d.add(String(W / 2, dpsi_y, dpsi_str,
                     fontSize=8, fontName="Helvetica-Bold",
                     fillColor=_colors.HexColor("#1e3a5f"), textAnchor="middle"))
        _add_star_pval(W / 2 + 52, dpsi_y - 1, "mean_delta_psi")

    # ── Exon size ★ ──
    _add_star_pval((SK_X1 + SK_X2) / 2, EXON_Y + EXON_H + 18, "exon_size")

    # ── Frame badge (directly under skipped exon) ──
    FRAME_Y = EXON_Y - 22
    FRAME_X = (SK_X1 + SK_X2) / 2
    # Percentage over events with a KNOWN frame class (unknown excluded)
    sig_known = (
        sig_data.get("frame_in_frame", 0)
        + sig_data.get("frame_frameshift", 0)
        + sig_data.get("frame_non_coding", 0)
    )
    if sig_known:
        sig_if_pct = sig_data.get("frame_in_frame", 0) / sig_known * 100
        frame_str = f"In-frame: {sig_if_pct:.0f}%"
    else:
        frame_str = "In-frame: n/a"
    badge_w = 90
    d.add(Rect(FRAME_X - badge_w / 2, FRAME_Y, badge_w, 16,
               fillColor=_colors.HexColor("#1e293b"), strokeColor=None, rx=4, ry=4))
    d.add(String(FRAME_X, FRAME_Y + 4, frame_str,
                 fontSize=7, fontName="Helvetica-Bold",
                 fillColor=_colors.HexColor("#86efac"), textAnchor="middle"))
    _add_star_pval(FRAME_X + badge_w / 2 + 6, FRAME_Y + 3, "in_frame_pct", anchor="start")

    # ── Splice site sequence boxes — SINGLE ROW ──
    SEQ_BOX_H = 16
    SEQ_FONT  = 6.5
    SEQ_Y = FRAME_Y - SEQ_BOX_H - 22

    def _draw_seq_box(x: float, y: float, consensus: str | None, label: str,
                      canonical_pos: set[int] | None = None, width: float = 0):
        seq = consensus or ""
        if not seq:
            return 0.0
        n = len(seq)
        cell_w = max(6.0, width / n) if width else 6.0
        box_w = n * cell_w
        # Box with subtle rounded corners
        d.add(Rect(x, y, box_w, SEQ_BOX_H,
                   fillColor=CLR_SEQ_BG, strokeColor=CLR_BORDER, strokeWidth=0.4, rx=2, ry=2))
        # Canonical position highlights
        if canonical_pos:
            for cp in canonical_pos:
                if 0 <= cp < n:
                    d.add(Rect(x + cp * cell_w, y, cell_w, SEQ_BOX_H,
                               fillColor=CLR_GT_BG, strokeColor=None))
        # Nucleotides
        for i, base in enumerate(seq):
            clr = _LOGO_BASE_COLOR_OBJS.get(base.upper(), CLR_TXT2)
            d.add(String(x + i * cell_w + cell_w / 2, y + 4, base.upper(),
                         fontSize=SEQ_FONT, fontName="Courier-Bold",
                         fillColor=clr, textAnchor="middle"))
        # Label above
        d.add(String(x + box_w / 2, y + SEQ_BOX_H + 5, label,
                     fontSize=6.5, fontName="Helvetica",
                     fillColor=CLR_TXT2, textAnchor="middle"))
        return box_w

    # All 4 sequences in one row, each centred on its junction
    # 1) Upstream 5'SS (donor) — centred on UP_X2
    up_donor_cons = sig_data.get("upstream_donor_consensus") or nonsig_data.get("upstream_donor_consensus")
    if up_donor_cons:
        n = len(up_donor_cons)
        bw = n * 6.0
        box_x = UP_X2 - bw / 2
        _draw_seq_box(box_x, SEQ_Y, up_donor_cons,
                      "Upstream 5'SS", canonical_pos={3, 4})
        _add_star_pval(UP_X2, SEQ_Y - 14, "upstream_canonical_gt")

    # 2) Skipped exon 3'SS (acceptor) — centred on SK_X1
    sk_acc_cons = sig_data.get("acceptor_consensus") or nonsig_data.get("acceptor_consensus")
    if sk_acc_cons:
        n = len(sk_acc_cons)
        # Fit between upstream donor and skipped donor
        max_w = INTRON_W + SKIP_W * 0.3
        acc_cell_w = min(6.0, max_w / n)
        acc_w = n * acc_cell_w
        acc_x = SK_X1 - acc_w / 2
        _draw_seq_box(acc_x, SEQ_Y, sk_acc_cons,
                      "Skipped 3'SS", canonical_pos={18, 19}, width=acc_w)
        _add_star_pval(SK_X1, SEQ_Y - 14, "canonical_ag")

    # 3) Skipped exon 5'SS (donor) — centred on SK_X2
    sk_don_cons = sig_data.get("donor_consensus") or nonsig_data.get("donor_consensus")
    if sk_don_cons:
        n = len(sk_don_cons)
        bw = n * 6.0
        don_x = SK_X2 - bw / 2
        _draw_seq_box(don_x, SEQ_Y, sk_don_cons,
                      "Skipped 5'SS", canonical_pos={3, 4})
        _add_star_pval(SK_X2, SEQ_Y - 14, "canonical_gt")

    # 4) Downstream 3'SS (acceptor) — centred on DN_X1
    dn_acc_cons = sig_data.get("downstream_acceptor_consensus") or nonsig_data.get("downstream_acceptor_consensus")
    if dn_acc_cons:
        n = len(dn_acc_cons)
        max_w = INTRON_W + FLANK_W * 0.3
        acc_cell_w = min(6.0, max_w / n)
        acc_w = n * acc_cell_w
        acc_x = DN_X1 - acc_w / 2
        _draw_seq_box(acc_x, SEQ_Y, dn_acc_cons,
                      "Downstream 3'SS", canonical_pos={18, 19}, width=acc_w)
        _add_star_pval(DN_X1, SEQ_Y - 14, "downstream_canonical_ag")

    # ── Dashed connector lines from junctions down to sequence boxes ──
    DASH = [2, 2]
    CONN_CLR = _colors.HexColor("#cbd5e1")
    for junc_x, has_seq in [(UP_X2, up_donor_cons), (SK_X1, sk_acc_cons),
                             (SK_X2, sk_don_cons), (DN_X1, dn_acc_cons)]:
        if has_seq:
            d.add(PolyLine([junc_x, EXON_Y, junc_x, SEQ_Y + SEQ_BOX_H],
                            strokeColor=CONN_CLR, strokeWidth=0.7, strokeDashArray=DASH))

    # ── PPT section (card-style, bottom-left) ──
    PPT_CARD_X = M_L
    PPT_CARD_Y = 18
    PPT_CARD_W = INTRON_W + FLANK_W + 20
    PPT_CARD_H = SEQ_Y - 30 - PPT_CARD_Y
    d.add(Rect(PPT_CARD_X, PPT_CARD_Y, PPT_CARD_W, PPT_CARD_H,
               fillColor=CLR_CARD, strokeColor=CLR_BORDER, strokeWidth=0.4, rx=4, ry=4))

    ppt_cx = PPT_CARD_X + PPT_CARD_W / 2
    ppt_top = PPT_CARD_Y + PPT_CARD_H

    # PPT title
    d.add(String(ppt_cx, ppt_top - 14, "Polypyrimidine Tract",
                 fontSize=8, fontName="Helvetica-Bold",
                 fillColor=CLR_TXT, textAnchor="middle"))

    # PPT progress bar
    PPT_BAR_W = PPT_CARD_W - 30
    PPT_BAR_H = 10
    bar_x = PPT_CARD_X + 15
    bar_y = ppt_top - 32
    d.add(Rect(bar_x, bar_y, PPT_BAR_W, PPT_BAR_H,
               fillColor=_colors.HexColor("#e2e8f0"), strokeColor=CLR_BORDER, strokeWidth=0.3, rx=3, ry=3))
    ppt_score = sig_data.get("ppt_mean_score")
    if ppt_score is not None:
        fill_w = ppt_score * PPT_BAR_W
        d.add(Rect(bar_x, bar_y, fill_w, PPT_BAR_H,
                   fillColor=CLR_PPT, strokeColor=None, rx=3, ry=3))
        d.add(String(bar_x + PPT_BAR_W / 2, bar_y + 2,
                     f"{ppt_score * 100:.0f}%", fontSize=7, fontName="Helvetica-Bold",
                     fillColor=_colors.HexColor("#78350f"), textAnchor="middle"))

    # T% and C% below bar
    ppt_t = sig_data.get("ppt_mean_t_content")
    ppt_c = sig_data.get("ppt_mean_c_content")
    tc_y = bar_y - 14
    tc_parts: list[str] = []
    if ppt_t is not None:
        tc_parts.append(f"T: {ppt_t * 100:.0f}%")
    if ppt_c is not None:
        tc_parts.append(f"C: {ppt_c * 100:.0f}%")
    if tc_parts:
        d.add(String(ppt_cx, tc_y, "   |   ".join(tc_parts),
                     fontSize=7, fontName="Helvetica",
                     fillColor=CLR_TXT, textAnchor="middle"))

    # PPT / T / C significance stars
    tc_feats = [("ppt_score", "PPT score"), ("ppt_t_content", "T content"), ("ppt_c_content", "C content")]
    sig_tc = [(f, lbl) for f, lbl in tc_feats if _star(f)]
    if sig_tc:
        star_str = "   ".join(f"★ {lbl}" for _, lbl in sig_tc)
        d.add(String(ppt_cx, tc_y - 14, star_str,
                     fontSize=6.5, fontName="Helvetica-Bold",
                     fillColor=CLR_SIG, textAnchor="middle"))

    # Branch point annotation
    bp_pct = sig_data.get("bp_found_pct")
    bp_test = test_map.get("bp_found")
    bp_is_sig = bp_test is not None and bp_test.get("significant", False)
    bp_pval = bp_test.get("p_value") if bp_test else None
    if bp_pct is not None:
        bp_y = PPT_CARD_Y + 10
        if bp_is_sig and bp_pval is not None:
            bp_label = f"Branch point: {bp_pct:.0f}%  ★ (p={bp_pval:.2e})"
        else:
            bp_label = f"Branch point: {bp_pct:.0f}%  (ns)"
        bp_clr = CLR_BP if bp_is_sig else CLR_TXT2
        d.add(String(ppt_cx, bp_y, bp_label,
                     fontSize=7, fontName="Helvetica", fillColor=bp_clr, textAnchor="middle"))

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
    svg_dir: str | None = None,
    selected_sections: set[str] | None = None,
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
        Each dict: {"iterations": int, "label": str | None, "n_tested": int,
                     "pct_p05": float, "pct_p01": float, "exact_fraction": float}.
        A single row with a "label" means all events were enumerated exactly.
    hnrnp_data : dict | None
        Result from hnRNP motif enrichment analysis.
        Keys: n_sig_events, n_bg_events, results (list of enrichment items).
    enrichr_data : dict | None
        Result from Enrichr pathway enrichment.
        Keys: n_genes_submitted, terms (list of EnrichrTermItem dicts).
    """
    if selected_sections is None:
        selected_sections = {"a", "b", "c", "d", "e", "f", "top_events"}

    # Thread-local figure counter: avoids data races when multiple PDF
    # requests are served concurrently via asyncio.to_thread.
    _fig_count: list[int] = [0]

    def _next_fig() -> int:
        _fig_count[0] += 1
        return _fig_count[0]

    def _save_svg(drawing: Drawing | None, name: str) -> None:
        """Save *drawing* as an SVG file inside *svg_dir* (no-op if either is None)."""
        if svg_dir is None or drawing is None:
            return
        try:
            os.makedirs(svg_dir, exist_ok=True)
            path = os.path.join(svg_dir, f"{name}.svg")
            _renderSVG.drawToFile(drawing, path)
        except Exception as exc:
            logger.warning("SVG export failed for %s: %s", name, exc)

    buf = BytesIO()
    USABLE_W = _W - 2 * _MARGIN          # ~15.27 cm
    FIG_MAX_W = USABLE_W                  # figures must not exceed this

    # Two page templates: portrait (default) and landscape (for schematic)
    _A4_LAND = _landscape(_A4)
    _frame_portrait = Frame(
        _MARGIN, _MARGIN, _A4[0] - 2 * _MARGIN, _A4[1] - 2 * _MARGIN,
        id="portrait_frame",
    )
    _frame_landscape = Frame(
        _MARGIN, _MARGIN, _A4_LAND[0] - 2 * _MARGIN, _A4_LAND[1] - 2 * _MARGIN,
        id="landscape_frame",
    )
    doc = BaseDocTemplate(
        buf,
        pagesize=_A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=_MARGIN,
    )
    doc.addPageTemplates([
        PageTemplate(id="portrait", frames=[_frame_portrait], pagesize=_A4),
        PageTemplate(id="landscape", frames=[_frame_landscape], pagesize=_A4_LAND),
    ])
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
    # Canonical-site flags can be None (unknown, truncated window): those
    # events are excluded from both numerator and denominator.
    n_gt = sum(1 for f in features.values() if f.donor_is_gt is True)
    n_gt_known = sum(1 for f in features.values() if f.donor_is_gt is not None)
    n_ag = sum(1 for f in features.values() if f.acceptor_is_ag is True)
    n_ag_known = sum(1 for f in features.values() if f.acceptor_is_ag is not None)
    story += [
        sp(0.3),
        p(f"<b>Total events:</b> {n_total} · <b>SE events:</b> {n_se}", "body"),
        p(f"<b>SE events with sequence data:</b> {n_with_seq} / {n_se}", "body"),
        p(f"<b>Canonical GT (5'SS):</b> {n_gt} / {n_gt_known} "
          f"({n_gt / n_gt_known * 100:.1f}%)", "body") if n_gt_known else sp(0),
        p(f"<b>Canonical AG (3'SS):</b> {n_ag} / {n_ag_known} "
          f"({n_ag / n_ag_known * 100:.1f}%)", "body") if n_ag_known else sp(0),
    ]

    story += [
        sp(0.5),
        p(
            "This report summarises the alternative splicing events identified "
            "by rMATS and annotated via rMATS-Viz (splice sites, reading frame, "
            "MANE transcript, PPT regions, branch point). "
            + ("Events are filtered by the deep analysis thresholds above. "
               if is_deep else "")
            + "All figures are vector graphics.",
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
            type_tbl = _make_tbl(
                [["Type", "Event Count", "% of Total"]] +
                [
                    [etype,
                     str(type_cnts.get(etype, 0)),
                     f"{type_cnts.get(etype, 0) / max(len(subset_events), 1) * 100:.1f}%"]
                    for etype in ["SE", "RI", "A3SS", "A5SS", "MXE"]
                ] +
                [[Paragraph("<b>Total</b>", S["body"]),
                  Paragraph(f"<b>{len(subset_events)}</b>", S["body"]),
                  Paragraph("<b>100%</b>", S["body"])]],
                [4 * _cm, 4 * _cm, 4 * _cm], S,
            )
            story += [sp(), type_tbl, sp()]

        if subset_features:
            n_f  = len(subset_features)
            # Canonical-site flags can be None (unknown): excluded from both
            # numerator and denominator.
            n_gt = sum(1 for f in subset_features.values() if f.donor_is_gt is True)
            n_gt_known = sum(1 for f in subset_features.values() if f.donor_is_gt is not None)
            n_ag = sum(1 for f in subset_features.values() if f.acceptor_is_ag is True)
            n_ag_known = sum(1 for f in subset_features.values() if f.acceptor_is_ag is not None)
            n_if = sum(1 for f in subset_features.values() if f.frame_class == "in_frame")
            n_fs = sum(1 for f in subset_features.values() if f.frame_class == "frameshift")
            n_nc = sum(1 for f in subset_features.values() if f.frame_class == "non_coding")
            n_frame_known = n_if + n_fs + n_nc
            n_frame_unknown = n_f - n_frame_known
            n_bp = sum(1 for f in subset_features.values() if f.bp_motif_found is True)
            n_bp_seq = sum(1 for f in subset_features.values() if f.ppt_seq)
            n_up_gt = sum(1 for f in subset_features.values() if f.upstream_donor_is_gt is True)
            n_up_seq = sum(1 for f in subset_features.values()
                           if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9
                           and f.upstream_donor_is_gt is not None)
            n_dn_ag = sum(1 for f in subset_features.values() if f.downstream_acceptor_is_ag is True)
            n_dn_seq = sum(1 for f in subset_features.values()
                           if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23
                           and f.downstream_acceptor_is_ag is not None)
            ppt_vals = [f.ppt_score for f in subset_features.values() if f.ppt_score is not None]
            ppt_t_vals = [_ppt_t_content(f.ppt_seq) for f in subset_features.values() if f.ppt_seq]
            ppt_c_vals = [_ppt_c_content(f.ppt_seq) for f in subset_features.values() if f.ppt_seq]
            exsz_vals = [f.exon_size for f in subset_features.values() if f.exon_size is not None]

            story.append(p("SE Splice Feature Statistics:", "h3"))
            stat_tbl = _make_tbl([
                ["Metric", "Value"],
                ["SE events with features", str(n_f)],
                ["Canonical GT (5'SS)", f"{n_gt} / {n_gt_known} ({n_gt / n_gt_known * 100:.1f}%)" if n_gt_known else "—"],
                ["Canonical AG (3'SS)", f"{n_ag} / {n_ag_known} ({n_ag / n_ag_known * 100:.1f}%)" if n_ag_known else "—"],
                ["Upstream GT (5'SS)", f"{n_up_gt} / {n_up_seq} ({n_up_gt / n_up_seq * 100:.1f}%)" if n_up_seq else "—"],
                ["Downstream AG (3'SS)", f"{n_dn_ag} / {n_dn_seq} ({n_dn_ag / n_dn_seq * 100:.1f}%)" if n_dn_seq else "—"],
                ["In-frame (of known frames)",   f"{n_if} / {n_frame_known} ({n_if / n_frame_known * 100:.0f}%)" if n_frame_known else "—"],
                ["Frameshift (of known frames)", f"{n_fs} / {n_frame_known} ({n_fs / n_frame_known * 100:.0f}%)" if n_frame_known else "—"],
                ["Non-coding (of known frames)", f"{n_nc} / {n_frame_known} ({n_nc / n_frame_known * 100:.0f}%)" if n_frame_known else "—"],
                ["Frame unknown (no MANE annotation)", f"{n_frame_unknown} / {n_f}" if n_f else "—"],
                ["Branch point detected", f"{n_bp} / {n_bp_seq} ({n_bp / n_bp_seq * 100:.1f}%)" if n_bp_seq else "—"],
                ["Exon size (mean / median)",
                 f"{_statistics.mean(exsz_vals):.0f} / {_statistics.median(exsz_vals):.0f} nt" if exsz_vals else "—"],
                ["Mean PPT score",
                 f"{_statistics.mean(ppt_vals) * 100:.1f}% pyrimidine content" if ppt_vals else "—"],
                ["Mean PPT T content",
                 f"{_statistics.mean(ppt_t_vals) * 100:.1f}%" if ppt_t_vals else "—"],
                ["Mean PPT C content",
                 f"{_statistics.mean(ppt_c_vals) * 100:.1f}%" if ppt_c_vals else "—"],
            ], [9 * _cm, 7 * _cm], S)
            story += [stat_tbl, sp()]

            if include_figures:
                dpsi_fig = _fig_dpsi_distribution(subset_events, group1_label)
                _save_svg(dpsi_fig, f"sec{section_num:02d}_dpsi_distribution")
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
                _save_svg(hist_fig, f"sec{section_num:02d}_exon_size_histogram")
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

                frame_fig = _fig_frame_breakdown(n_if, n_fs, n_nc, n_frame_unknown)
                _save_svg(frame_fig, f"sec{section_num:02d}_reading_frame")
                if frame_fig:
                    story += [
                        KeepTogether([
                            frame_fig,
                            caption(
                                "Reading-frame classification of skipped exons. "
                                "In-frame: CDS length divisible by 3; frameshift: not divisible by 3; "
                                "non-coding: exon entirely within UTR. Percentages are computed over "
                                f"events with a known frame class (n = {n_frame_known}); "
                                f"{n_frame_unknown} unknown (no MANE annotation) are excluded."
                            ),
                        ]),
                        sp(),
                    ]

                n_donor = sum(1 for f in subset_features.values() if f.donor_seq and len(f.donor_seq) >= 9)
                donor_logo = _fig_splice_site_consensus(subset_features, site="donor", n_sequences=n_donor, max_width=FIG_MAX_W)
                _save_svg(donor_logo, f"sec{section_num:02d}_5ss_donor_logo")
                if donor_logo:
                    story += [
                        KeepTogether([
                            donor_logo,
                            caption(
                                "Skipped exon 5'SS donor splice site sequence logo (9 nt: 3 nt exon + 6 nt intron). "
                                "Letter height ∝ nucleotide frequency (frequency mode; columns always full height; no IC scaling). "
                                "Canonical GT at positions +1/+2 highlighted in yellow. "
                                f"n = {n_donor} sequences."
                            ),
                        ]),
                        sp(),
                    ]

                n_acc = sum(1 for f in subset_features.values() if f.acceptor_seq and len(f.acceptor_seq) >= 23)
                acceptor_logo = _fig_splice_site_consensus(subset_features, site="acceptor", n_sequences=n_acc, max_width=FIG_MAX_W)
                _save_svg(acceptor_logo, f"sec{section_num:02d}_3ss_acceptor_logo")
                if acceptor_logo:
                    story += [
                        KeepTogether([
                            acceptor_logo,
                            caption(
                                "Skipped exon 3'SS acceptor splice site sequence logo (23 nt: 20 nt intron + 3 nt exon). "
                                "Letter height ∝ nucleotide frequency (frequency mode; columns always full height; no IC scaling). "
                                "Canonical AG at positions -2/-1 highlighted in yellow. "
                                f"n = {n_acc} sequences."
                            ),
                        ]),
                        sp(),
                    ]

                # Flanking exon — upstream donor 5'SS
                up_seqs = [f.upstream_donor_seq[:9].upper() for f in subset_features.values()
                           if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9]
                if len(up_seqs) >= 3:
                    up_pwm = _compute_pwm(up_seqs)
                    up_logo = _fig_splice_site_consensus(
                        {}, site="donor", pwm_data=up_pwm,
                        n_sequences=len(up_seqs), max_width=FIG_MAX_W,
                    )
                    _save_svg(up_logo, f"sec{section_num:02d}_upstream_5ss_donor_logo")
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
                    dn_pwm = _compute_pwm(dn_seqs)
                    dn_logo = _fig_splice_site_consensus(
                        {}, site="acceptor", pwm_data=dn_pwm,
                        n_sequences=len(dn_seqs), max_width=FIG_MAX_W,
                    )
                    _save_svg(dn_logo, f"sec{section_num:02d}_downstream_3ss_acceptor_logo")
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
    section_n = 1
    if "a" in selected_sections:
        section_n = _add_stats_and_figures(features, events, section_n, "Global Analysis Summary")

    # ── Section B: Significant Events (deep analysis only) ─────────────────
    if "b" in selected_sections and is_deep and sig_map:
        story.append(PageBreak())
        sig_feat_dict = {eid: f for eid, f in features.items() if sig_map.get(eid)}
        sig_evts = [e for e in events if sig_map.get(e.id)]
        section_n = _add_stats_and_figures(
            sig_feat_dict, sig_evts, section_n,
            f"Significant Events (FDR ≤ {deep_analysis.fdr_threshold}, |ΔΨ| ≥ {deep_analysis.delta_psi_min})",
        )

    # ── Section C: Comparison (deep analysis only) ─────────────────────────
    if "c" in selected_sections and comparison:
        story.append(PageBreak())
        cmp_sec = section_n
        story.append(p(f"{cmp_sec}. Significant vs Non-Significant Comparison", "h2"))
        section_n += 1

        sig = comparison["significant"]
        nonsig = comparison["not_significant"]
        tests = comparison.get("statistical_tests", [])
        test_map = {t["feature"]: t for t in tests}
        n_tests = len(tests)
        n_tests_run = sum(1 for t in tests if t.get("p_value") is not None)

        def _fmt_pval(pv):
            if pv is None:
                return "—"
            if pv < 0.0001:
                return f"{pv:.2e}"
            return f"{pv:.4f}"

        def _sig_str(t):
            if t is None or t.get("p_value") is None:
                return ""
            raw = "★" if t.get("significant") else "n.s."
            if t.get("significant_fdr"):
                raw += "†"
            return raw

        def _test_label(t):
            if not t:
                return "—"
            name = t.get("test_name", "—")
            return "Mann-Whitney U" if name == "mann_whitney_u" else name

        # Ca. Feature comparison table
        cmp_headers = ["Feature", f"Significant (n={sig['n_se_with_features']})",
                        f"Non-significant (n={nonsig['n_se_with_features']})", "Test", "p-value", "q (BH)", ""]
        cmp_rows = [cmp_headers]

        def _row(label, sig_val, nonsig_val, test_key):
            """Append one row per test available for *test_key*: the primary
            test and, for continuous features, the Mann-Whitney U row."""
            keys = [test_key]
            if f"{test_key}_mwu" in test_map:
                keys.append(f"{test_key}_mwu")
            for i, key in enumerate(keys):
                t = test_map.get(key)
                cmp_rows.append([
                    label if i == 0 else "",
                    (sig_val if sig_val is not None else "—") if i == 0 else "",
                    (nonsig_val if nonsig_val is not None else "—") if i == 0 else "",
                    _test_label(t),
                    _fmt_pval(t["p_value"] if t else None),
                    _fmt_pval(t.get("q_value") if t else None),
                    _sig_str(t),
                ])

        def _pct(v):
            return f"{v:.1f}%" if v is not None else "—"

        def _frame_pct(g):
            known = g.get("frame_in_frame", 0) + g.get("frame_frameshift", 0) + g.get("frame_non_coding", 0)
            return g.get("frame_in_frame", 0) / known * 100 if known else None

        _row("Exon size (mean)", f"{sig['exon_size_mean']:.0f} nt" if sig.get("exon_size_mean") else "—",
             f"{nonsig['exon_size_mean']:.0f} nt" if nonsig.get("exon_size_mean") else "—", "exon_size")
        _row("Canonical GT", _pct(sig.get("pct_canonical_gt")), _pct(nonsig.get("pct_canonical_gt")), "canonical_gt")
        _row("Canonical AG", _pct(sig.get("pct_canonical_ag")), _pct(nonsig.get("pct_canonical_ag")), "canonical_ag")
        _row("Mean PPT score", _pct(sig["ppt_mean_score"] * 100 if sig.get("ppt_mean_score") is not None else None),
             _pct(nonsig["ppt_mean_score"] * 100 if nonsig.get("ppt_mean_score") is not None else None), "ppt_score")
        _row("PPT T content", _pct(sig["ppt_mean_t_content"] * 100 if sig.get("ppt_mean_t_content") is not None else None),
             _pct(nonsig["ppt_mean_t_content"] * 100 if nonsig.get("ppt_mean_t_content") is not None else None), "ppt_t_content")
        _row("PPT C content", _pct(sig["ppt_mean_c_content"] * 100 if sig.get("ppt_mean_c_content") is not None else None),
             _pct(nonsig["ppt_mean_c_content"] * 100 if nonsig.get("ppt_mean_c_content") is not None else None), "ppt_c_content")
        _row("In-frame % (of known frames)", _pct(_frame_pct(sig)), _pct(_frame_pct(nonsig)), "in_frame_pct")
        _row("Branch point found", _pct(sig.get("bp_found_pct")), _pct(nonsig.get("bp_found_pct")), "bp_found")
        _row("Mean ΔΨ",
             f"{sig['mean_delta_psi']:+.3f}" if sig.get("mean_delta_psi") is not None else "—",
             f"{nonsig['mean_delta_psi']:+.3f}" if nonsig.get("mean_delta_psi") is not None else "—",
             "mean_delta_psi")
        _row("Upstream GT (5'SS)", _pct(sig.get("pct_upstream_gt")), _pct(nonsig.get("pct_upstream_gt")), "upstream_canonical_gt")
        _row("Downstream AG (3'SS)", _pct(sig.get("pct_downstream_ag")), _pct(nonsig.get("pct_downstream_ag")), "downstream_canonical_ag")
        _row("Upstream intron (mean)",
             f"{sig['upstream_intron_size_mean']:.0f} nt" if sig.get("upstream_intron_size_mean") is not None else "—",
             f"{nonsig['upstream_intron_size_mean']:.0f} nt" if nonsig.get("upstream_intron_size_mean") is not None else "—",
             "upstream_intron_size")
        _row("Downstream intron (mean)",
             f"{sig['downstream_intron_size_mean']:.0f} nt" if sig.get("downstream_intron_size_mean") is not None else "—",
             f"{nonsig['downstream_intron_size_mean']:.0f} nt" if nonsig.get("downstream_intron_size_mean") is not None else "—",
             "downstream_intron_size")

        cmp_tbl = _make_tbl(cmp_rows, [3.0*_cm, 2.9*_cm, 2.9*_cm, 2.6*_cm, 1.9*_cm, 1.9*_cm, 1.0*_cm], S)
        _sig_unknown_note = ""
        _fr_unk_sig = sig.get("n_se_with_features", 0) - (
            sig.get("frame_in_frame", 0) + sig.get("frame_frameshift", 0) + sig.get("frame_non_coding", 0))
        _fr_unk_ns = nonsig.get("n_se_with_features", 0) - (
            nonsig.get("frame_in_frame", 0) + nonsig.get("frame_frameshift", 0) + nonsig.get("frame_non_coding", 0))
        if _fr_unk_sig or _fr_unk_ns:
            _sig_unknown_note = (
                f" In-frame % excludes events with an unknown frame "
                f"({_fr_unk_sig} significant, {_fr_unk_ns} non-significant)."
            )
        story += [KeepTogether([
            p(f"{cmp_sec}.1 Feature Comparison", "h3"),
            cmp_tbl,
            p("★ = raw p &lt; 0.05; † = Benjamini-Hochberg q &lt; 0.05; n.s. = not significant. "
              f"{n_tests} tests in this panel ({n_tests_run} evaluable); q-values are BH-adjusted "
              "across the whole panel. Continuous features are tested with both Welch's t-test "
              "(assumes approximate normality) and the rank-based Mann-Whitney U test, which is "
              "robust to the right-skew of exon/intron size distributions; proportion tests require "
              "≥ 5 events per group." + _sig_unknown_note, "small"),
        ]), sp()]

        # Cb. Comparison logos — donor
        half_w = FIG_MAX_W
        _block: list = [p(f"{cmp_sec}.2 5'SS Donor Logo: Significant vs Non-Significant", "h3")]
        if sig.get("donor_pwm"):
            d_sig = _fig_splice_site_consensus(
                {}, site="donor", pwm_data=sig["donor_pwm"],
                n_sequences=sig["n_se_with_features"], max_width=half_w,
            )
            _save_svg(d_sig, f"sec{cmp_sec:02d}_comparison_5ss_donor_sig")
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
            _save_svg(d_nonsig, f"sec{cmp_sec:02d}_comparison_5ss_donor_nonsig")
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
            "Letter height ∝ nucleotide frequency (frequency mode; columns always full height; no IC scaling). "
            "Canonical GT at positions +1/+2 highlighted."
        ))
        story += [KeepTogether(_block), sp()]

        # Cc. Comparison logos — acceptor
        _block = [p(f"{cmp_sec}.3 3'SS Acceptor Logo: Significant vs Non-Significant", "h3")]
        if sig.get("acceptor_pwm"):
            a_sig = _fig_splice_site_consensus(
                {}, site="acceptor", pwm_data=sig["acceptor_pwm"],
                n_sequences=sig["n_se_with_features"], max_width=half_w,
            )
            _save_svg(a_sig, f"sec{cmp_sec:02d}_comparison_3ss_acceptor_sig")
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
            _save_svg(a_nonsig, f"sec{cmp_sec:02d}_comparison_3ss_acceptor_nonsig")
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
            "Letter height ∝ nucleotide frequency (frequency mode; columns always full height; no IC scaling). "
            "Canonical AG at positions -2/-1 highlighted."
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
                _save_svg(ud_sig, f"sec{cmp_sec:02d}_comparison_upstream_donor_sig")
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
                _save_svg(ud_nonsig, f"sec{cmp_sec:02d}_comparison_upstream_donor_nonsig")
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
                _save_svg(da_sig, f"sec{cmp_sec:02d}_comparison_downstream_acceptor_sig")
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
                _save_svg(da_nonsig, f"sec{cmp_sec:02d}_comparison_downstream_acceptor_nonsig")
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

        # Cf. Frame comparison (percentages over KNOWN frames; unknown shown beside the bar)
        _block = [p(f"{cmp_sec}.6 Reading Frame Comparison", "h3")]
        frame_sig = _fig_frame_breakdown(sig["frame_in_frame"], sig["frame_frameshift"], sig["frame_non_coding"], _fr_unk_sig)
        _save_svg(frame_sig, f"sec{cmp_sec:02d}_comparison_reading_frame_sig")
        if frame_sig:
            _block += [p(f"<b>Significant</b> (n = {sig['n_se_with_features']}, {_fr_unk_sig} unknown)", "small"), frame_sig]
        frame_nonsig = _fig_frame_breakdown(nonsig["frame_in_frame"], nonsig["frame_frameshift"], nonsig["frame_non_coding"], _fr_unk_ns)
        _save_svg(frame_nonsig, f"sec{cmp_sec:02d}_comparison_reading_frame_nonsig")
        if frame_nonsig:
            _block += [p(f"<b>Non-significant</b> (n = {nonsig['n_se_with_features']}, {_fr_unk_ns} unknown)", "small"), frame_nonsig]
        t_frame = test_map.get("in_frame_pct")
        if t_frame:
            _block.append(p(
                f"In-frame proportion — {t_frame['test_name']}: "
                f"p = {_fmt_pval(t_frame['p_value'])} "
                f"({'significant' if t_frame['significant'] else 'not significant'})",
                "small",
            ))
        _block.append(caption(
            "Reading-frame breakdown: significant vs non-significant events. "
            "Percentages are computed over events with a known frame class; "
            "events without MANE annotation (unknown) are counted beside each bar and excluded."
        ))
        story += [KeepTogether(_block), sp()]

    # ── Section D: Permutation Test (deep analysis only) ──────────────────
    if "d" in selected_sections and permutation_table:
        story.append(PageBreak())
        perm_sec = section_n
        story.append(p(f"{perm_sec}. Permutation Test — ΔΨ Significance", "h2"))
        section_n += 1

        story.append(p(
            "The permutation test evaluates whether the observed ΔΨ for each event is "
            "statistically significant by permuting sample labels and computing a null "
            "distribution.  When the number of distinct label splits C(n1+n2, n1) is ≤ 5000 "
            "every split is enumerated (exact p = r / N); otherwise Monte-Carlo sampling is "
            "used with p = (r + 1) / (K + 1).  The table below shows the percentage of events "
            "reaching significance at different iteration counts K, providing insight into "
            "result stability as the number of permutations increases (rows are identical "
            "when all events are enumerated exactly, since K is then irrelevant).",
            "body",
        ))
        story.append(sp())

        perm_headers = ["Iterations (K)", "Events Tested", "% p < 0.05", "% p < 0.01", "Exact"]
        perm_rows = [perm_headers]
        for pt in permutation_table:
            ef = pt.get("exact_fraction")
            perm_rows.append([
                pt.get("label") or f"{pt['iterations']:,}",
                f"{pt['n_tested']:,}",
                f"{pt['pct_p05']:.1f}%" if pt.get("pct_p05") is not None else "—",
                f"{pt['pct_p01']:.1f}%" if pt.get("pct_p01") is not None else "—",
                f"{ef * 100:.0f}%" if ef is not None else "—",
            ])
        perm_tbl = _make_tbl(perm_rows, [3.0 * _cm, 3.0 * _cm, 3.0 * _cm, 3.0 * _cm, 2.5 * _cm], S)
        story += [perm_tbl, sp()]

        _ref = permutation_table[-1]
        _min_p = _ref.get("min_p_attainable")
        _n_g1 = _ref.get("n_replicates_g1")
        _n_g2 = _ref.get("n_replicates_g2")
        _design = (
            f" Replicate design: {_n_g1} vs {_n_g2} per group."
            if _n_g1 is not None and _n_g2 is not None else ""
        )
        _min_p_txt = (
            f" <b>Minimum attainable p-value: {_min_p:.4g}</b> — with few replicates per group "
            "only a handful of distinct label splits exist, so p-values below this bound are "
            "impossible whatever the number of iterations; interpret '% p &lt; 0.01' accordingly."
            if _min_p is not None else ""
        )
        story.append(p(
            "As the number of Monte-Carlo iterations increases, the empirical p-value "
            "estimates become more precise; convergence of the significance percentages "
            "across iterations indicates stable results.  'Exact' is the fraction of events "
            "whose p-value comes from complete enumeration." + _design + _min_p_txt,
            "small",
        ))
        story.append(sp())

    # ── Section E: hnRNP Motif Enrichment (deep analysis only) ─────────────
    if "e" in selected_sections and hnrnp_data:
        story.append(PageBreak())
        hnrnp_sec = section_n
        section_n += 1
        story.append(p(f"{hnrnp_sec}. hnRNP Motif Enrichment Analysis", "h2"))
        _hn_regions = _heatmap_region_order(hnrnp_data)
        story.append(p(
            f"Inspired by rMAPS2 (Hwang et al., 2020), this analysis scans {len(_hn_regions)} genomic "
            "regions around each skipped exon (upstream exon; upstream intron on the 5'SS and on the "
            "3'SS side; skipped exon; downstream intron on the 5'SS and on the 3'SS side; downstream "
            "exon) for known hnRNP RNA-binding protein consensus motifs and compares significant and "
            "non-significant events with two complementary tests: motif <i>presence</i> (fraction of "
            "events with ≥ 1 hit, two-proportion z-test) and motif <i>density</i> (hits per nt per "
            "event, Mann-Whitney U test).  Each family of p-values is Benjamini-Hochberg adjusted "
            "across all motif × region pairs (q &lt; 0.05).",
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

        _hn_headers = ["Protein", "Motif", "Region", "Sig %", "Bg %", "z", "q presence", "q density"]
        _hn_widths = [2.5*_cm, 1.7*_cm, 3.3*_cm, 1.4*_cm, 1.4*_cm, 1.2*_cm, 2.0*_cm, 2.0*_cm]

        def _fmt_q(v):
            if v is None:
                return "—"
            return f"{v:.2e}" if v < 0.001 else f"{v:.4f}"

        def _hn_row(r: dict) -> list:
            sig_pct = f"{r['sig_hit_count'] / r['sig_total'] * 100:.1f}%" if r.get("sig_total") else "—"
            bg_pct = f"{r['bg_hit_count'] / r['bg_total'] * 100:.1f}%" if r.get("bg_total") else "—"
            z_str = f"{r['z_stat']:.2f}" if r.get("z_stat") is not None else "—"
            q_dens = _fmt_q(r.get("density_p_adjusted"))
            if r.get("density_significant"):
                q_dens = f"<b>{q_dens}</b>"
            return [
                r.get("protein", "—"),
                r.get("motif_name", "—"),
                _REGION_TABLE_LABELS.get(r.get("region", ""), r.get("region", "—")),
                sig_pct,
                bg_pct,
                z_str,
                _fmt_q(r.get("p_adjusted")),
                q_dens,
            ]

        sig_motifs = [
            r for r in hnrnp_data.get("results", [])
            if r.get("significant") or r.get("density_significant")
        ]
        if sig_motifs:
            # Sort by the smaller of the two adjusted p-values
            sig_motifs_sorted = sorted(
                sig_motifs,
                key=lambda r: (
                    min(r.get("p_adjusted") if r.get("p_adjusted") is not None else 1.0,
                        r.get("density_p_adjusted") if r.get("density_p_adjusted") is not None else 1.0),
                    r.get("region", ""), r.get("motif_name", ""),
                ),
            )
            hnrnp_rows = [_hn_headers] + [_hn_row(r) for r in sig_motifs_sorted[:30]]  # top 30
            hnrnp_tbl = _make_tbl(hnrnp_rows, _hn_widths, S)
            story += [hnrnp_tbl, sp(0.2)]
            n_pres = sum(1 for r in sig_motifs if r.get("significant"))
            n_dens = sum(1 for r in sig_motifs if r.get("density_significant"))
            story.append(p(
                f"Showing {min(len(sig_motifs_sorted), 30)} of {len(sig_motifs)} motif-region "
                f"associations significant in at least one test (presence: {n_pres}; density: {n_dens}; "
                "BH q &lt; 0.05). Sig % / Bg % = percentage of events with at least one motif hit; "
                "z = presence z-statistic; q presence = BH-adjusted p of the two-proportion z-test; "
                "q density = BH-adjusted p of the Mann-Whitney U test on per-event densities "
                "(bold when q &lt; 0.05).",
                "small",
            ))
        else:
            story.append(p(
                "No motif-region combinations reached significance in either the presence or the "
                "density test after Benjamini-Hochberg FDR correction (q &lt; 0.05).",
                "body",
            ))

        # ── Heatmap: protein × region (best motif per cell) ────────────────
        heatmap_drawing = _build_hnrnp_heatmap(hnrnp_data)
        if heatmap_drawing:
            story.append(sp(0.4))
            story.append(KeepTogether([
                p("Enrichment Heatmap — Best Motif per Protein × Region", "h3"),
                heatmap_drawing,
                sp(0.15),
                p(
                    "<font color='#dc2626'>■</font> Enriched in sig. &nbsp; "
                    "<font color='#2563eb'>■</font> Depleted in sig. &nbsp; "
                    "<font color='#94a3b8'>■</font> n.s. &nbsp;&nbsp; "
                    "<font color='#ea580c'>▬</font> Silencer (ESS/ISS) &nbsp; "
                    "<font color='#059669'>▬</font> Enhancer (ESE/ISE)",
                    "small",
                ),
            ]))
        story.append(sp(0.3))

        # ── Non-significant motifs (complete search overview) ────────────────
        nonsig_motifs = [
            r for r in hnrnp_data.get("results", [])
            if not r.get("significant") and not r.get("density_significant")
        ]
        if nonsig_motifs:
            story.append(sp(0.3))
            story.append(p("All Non-Significant Motif-Region Associations", "h3"))
            story.append(p(
                "The following motif-region pairs were tested but did not reach significance "
                "in either test after Benjamini-Hochberg FDR correction (q ≥ 0.05).",
                "body",
            ))
            nonsig_motifs_sorted = sorted(
                nonsig_motifs,
                key=lambda r: (
                    min(r.get("p_adjusted") if r.get("p_adjusted") is not None else 1.0,
                        r.get("density_p_adjusted") if r.get("density_p_adjusted") is not None else 1.0),
                    r.get("region", ""), r.get("motif_name", ""),
                ),
            )
            nonsig_hnrnp_rows = [_hn_headers] + [_hn_row(r) for r in nonsig_motifs_sorted]
            nonsig_hnrnp_tbl = _make_tbl(nonsig_hnrnp_rows, _hn_widths, S)
            story += [nonsig_hnrnp_tbl, sp(0.2)]
            story.append(p(
                f"{len(nonsig_motifs)} motif-region associations shown. "
                "Sig % / Bg % = percentage of events with at least one motif hit; "
                "q presence / q density as above.",
                "small",
            ))
        story.append(sp())

    # ── Section F: Enrichr Pathway Enrichment (deep analysis only) ─────────
    if "f" in selected_sections and enrichr_data and enrichr_data.get("terms"):
        story.append(PageBreak())
        enr_sec = section_n
        section_n += 1
        n_genes = enrichr_data.get("n_genes_submitted", 0)
        story.append(p(f"{enr_sec}. Pathway Enrichment Analysis (Enrichr)", "h2"))
        story.append(p(
            f"Gene symbols from significant events (n = {n_genes} unique genes) were submitted "
            "to the Enrichr REST API (Ma'ayan Lab). Enrichment was computed against five curated "
            "gene-set libraries: KEGG 2021, GO Biological Process, GO Molecular Function, "
            "Reactome 2022, and WikiPathways 2023. The combined score = log(p) × z "
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
        # Show top 10 per library (by adjusted p-value)
        _ENRICHR_TOP_N = 10
        by_lib: dict[str, list] = {}
        for term in enrichr_data.get("terms", []):
            lib = term.get("library", "Unknown")
            by_lib.setdefault(lib, []).append(term)

        for lib, terms in by_lib.items():
            top_terms = sorted(terms, key=lambda t: t.get("adjusted_p_value", 1.0))[:_ENRICHR_TOP_N]
            lib_label = _lib_labels.get(lib, lib)
            story.append(p(lib_label, "h3"))
            enr_headers = ["Rank", "Term", "Overlap", "Adj. p-value", "Combined Score"]
            enr_rows = [enr_headers]
            for term in top_terms:
                adj_p = term.get("adjusted_p_value", 1.0)
                p_str = f"{adj_p:.2e}" if adj_p < 0.001 else f"{adj_p:.4f}"
                if adj_p < 0.05:
                    p_str = f"<b>&#9733; {p_str}</b>"
                enr_rows.append([
                    str(term.get("rank", "—")),
                    str(term.get("term", "—")),
                    str(term.get("overlap", "—")),
                    p_str,
                    f"{term.get('combined_score', 0.0):.1f}",
                ])
            enr_tbl = _make_tbl(enr_rows, [1.0*_cm, 7.5*_cm, 1.8*_cm, 2.2*_cm, 2.7*_cm], S)
            story += [enr_tbl, sp(0.2)]
            # List genes per significant term (adj. p < 0.05)
            for term in top_terms:
                if term.get("adjusted_p_value", 1.0) < 0.05 and term.get("genes"):
                    genes_sorted = sorted(term["genes"])
                    term_name = str(term.get("term", "—"))
                    story.append(p(
                        f"<b>{term_name}:</b> {', '.join(genes_sorted)}",
                        "small",
                    ))
            story.append(sp(0.15))
        story.append(p(
            "FDR-adjusted p-values use the Benjamini-Hochberg method (Enrichr internal correction). "
            f"Top {_ENRICHR_TOP_N} terms per library shown (ranked by adjusted p-value). "
            "Overlap = k/n (k overlapping genes / n genes in the set; n omitted when the "
            "library GMT could not be retrieved). <b>&#9733;</b> Adj. p-value &lt; 0.05.",
            "small",
        ))
        story.append(sp())

    # ── Top SE events ──────────────────────────────────────────────────────
    if "top_events" in selected_sections:
        story.append(PageBreak())
        _top_title = "Top Significant SE Events (ranked by FDR, |ΔΨ|)" if is_deep else "Top SE Events (ranked by FDR, |ΔΨ|)"
        story.append(p(f"{section_n}. {_top_title}", "h2"))
        section_n += 1
        top_se = sorted(
            [
                e for e in events
                if e.event_type == "SE" and e.fdr is not None
                and (not is_deep or sig_map is None or sig_map.get(e.id, False))
            ],
            key=lambda e: (e.fdr if e.fdr is not None else 1.0, -(abs(e.inc_level_difference or 0))),
        )[:20]

        if top_se:
            top_headers = ["Gene", "Chr", "Strand", "Exon\nSize", "FDR", "ΔΨ", "GT-AG", "Frame"]
            top_rows = [top_headers]
            for ev in top_se:
                feat = features.get(ev.id)
                gt_ag = "—"
                if feat:
                    # None = window unavailable / truncated (unknown), not "!GT"
                    gt = "?" if feat.donor_is_gt is None else ("GT" if feat.donor_is_gt else "!GT")
                    ag = "?" if feat.acceptor_is_ag is None else ("AG" if feat.acceptor_is_ag else "!AG")
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
            top_tbl = _make_tbl(top_rows, [2.8*_cm, 1.8*_cm, 1*_cm, 1.8*_cm, 2.2*_cm, 1.8*_cm, 1.8*_cm, 2*_cm], S)
            story += [top_tbl, sp()]
        else:
            story.append(p("No SE events available.", "body"))

        # ── Events with MANE flanking-based exon correction ───────────────────
        flanking_events = sorted(
            [
                (ev, features.get(ev.id))
                for ev in events
                if ev.event_type == "SE"
                and features.get(ev.id) is not None
                and getattr(features.get(ev.id), "mane_exon_source", None) == "flanking"
            ],
            key=lambda pair: (pair[0].gene_symbol or "", pair[0].chr or "", pair[0].exon_start or 0),
        )
        if flanking_events:
            story.append(sp())
            story.append(p(
                "<b>Note:</b> Exon coordinate correction via MANE flanking method",
                "h3",
            ))
            story.append(p(
                "The following events have skipped-exon coordinates in rMATS that differ "
                "from the MANE Select transcript boundaries. Because the standard overlap "
                "matching (reciprocal ≥ 50%) could not identify the correct MANE exon, "
                "the consensual exon was selected based on its position between the upstream "
                "and downstream flanking exon boundaries (derived from junction reads). "
                "Splice-site sequences for these events were extracted using the MANE exon "
                "coordinates rather than the original rMATS coordinates.",
                "body",
            ))
            flk_headers = ["Gene", "Chr", "Strand", "rMATS Exon", "MANE Transcript"]
            flk_rows = [flk_headers]
            for ev, feat in flanking_events[:30]:  # cap at 30 to avoid page overflow
                rmats_exon = (
                    f"{(ev.exon_start or 0):,}–{(ev.exon_end or 0):,}"
                    if ev.exon_start is not None else "—"
                )
                flk_rows.append([
                    ev.gene_symbol or "—",
                    ev.chr or "—",
                    ev.strand or "—",
                    rmats_exon,
                    feat.mane_transcript_id or "—",
                ])
            flk_tbl = _make_tbl(flk_rows, [2.8*_cm, 1.8*_cm, 1*_cm, 4.2*_cm, 4.2*_cm], S)
            story += [flk_tbl, sp(0.2)]
            if len(flanking_events) > 30:
                story.append(p(
                    f"… and {len(flanking_events) - 30} more events (not shown).",
                    "small",
                ))
            story.append(sp())

    # ── Summary Schematic (deep analysis only, landscape page) ─────────────
    if comparison:
        # Switch to landscape for the schematic
        story.append(NextPageTemplate("landscape"))
        story.append(PageBreak())
        section_n += 1
        _schem = _fig_summary_schematic(
            comparison,
            comparison["significant"],
            comparison["not_significant"],
            group1_label=group1_label,
        )
        if _schem:
            _save_svg(_schem, f"sec{section_n - 1:02d}_summary_schematic")
            _legend_html = (
                '<font size="6">'
                '<font color="#dc2626"><b>★</b></font> Significant (p &lt; 0.05) &nbsp;&nbsp; '
                '<font color="#94a3b8"><b>■</b></font> Flanking exon &nbsp;&nbsp; '
                '<font color="#6366f1"><b>■</b></font> Skipped exon &nbsp;&nbsp; '
                '<font color="#a78bfa"><b>---</b></font> Skipping arc &nbsp;&nbsp; '
                '<font color="#f59e0b"><b>■</b></font> PPT score &nbsp;&nbsp; '
                '<font color="#22c55e"><b>BP</b></font> Branch point'
                '</font>'
            )
            _legend_style = ParagraphStyle(
                "SchematicLegend", parent=S["small"],
                fontSize=6, leading=8, alignment=TA_CENTER,
                textColor=_colors.HexColor("#475569"),
            )
            story.append(KeepTogether([
                p(f"{section_n - 1}. Summary Schematic", "h2"),
                sp(0.15),
                _schem,
                sp(0.1),
                Paragraph(_legend_html, _legend_style),
                sp(0.1),
                caption(
                    f"Schematic representation of skipped-exon features in significant events "
                    f"identified in {group1_label} subjects. Consensus splice-site sequences, "
                    f"PPT score, reading frame, and branch-point detection rate are shown. "
                    f"Red stars (★) indicate features for which a statistically significant "
                    f"difference (raw p &lt; 0.05) was found compared to background events "
                    f"(non-significant exon-skipping events, filtered by FDR and ΔΨ thresholds). "
                    f"Each feature was tested individually (Welch's t-test and Mann-Whitney U for "
                    f"continuous variables; two-proportion z-test for categorical variables; "
                    f"stars reflect the primary test, see the comparison table for BH q-values). "
                    f"In-frame % is computed over events with a known frame class. "
                    f"No correlation between features and no multiparametric test was performed."
                ),
            ]))
        # Switch back to portrait for subsequent pages
        story.append(NextPageTemplate("portrait"))
        story.append(sp())

    story.append(PageBreak())

    # ── Appendix A — Methodology ────────────────────────────────────────────
    # Subsections 1-5: always include if section A or B selected
    # Subsection 6 (Deep Analysis): include if section C selected
    # Subsection 7 (Permutation): include if section D selected
    # Subsection 8 (hnRNP): include if section E selected
    # Subsection 9 (Enrichr): include if section F selected
    _app_a_n = [0]  # dynamic counter for appendix A subsections

    def _next_app_a() -> int:
        _app_a_n[0] += 1
        return _app_a_n[0]

    story += [
        p("Appendix A — Pipeline Methodology", "h2"),
        hr(),
    ]

    # ── Introductory paragraph: raw file preprocessing ──
    _n = _next_app_a()
    story += [
        p(f"<b>{_n}. Input Preprocessing — Coverage Filtering &amp; Deduplication</b>", "h3"),
        p("Upon import, each rMATS output file (<i>.MATS.JC.txt</i>) undergoes two "
          "successive preprocessing steps before any downstream analysis:", "body"),
        p("• <b>Coverage filtering:</b> For each event, the mean per-replicate "
          "junction coverage (IJC + SJC) is computed in both sample groups. Events "
          "whose mean coverage falls below <b>10 reads</b> in either group are "
          "discarded to ensure reliable Ψ estimates.", "body"),
        p("• <b>Type-aware deduplication:</b> Within each (event type, gene, "
          "chromosome, strand) group, near-duplicate events were collapsed by retaining "
          "the event with the lowest FDR (ties broken by largest |ΔΨ|). The "
          "near-duplicate rule depends on the event type: <b>SE</b> — at least one "
          "skipped-exon boundary (start <i>or</i> end) within <b>±50 bp</b>; <b>RI</b> — "
          "both boundaries of the retained intron within ±50 bp (<i>and</i>); <b>MXE</b> — "
          "all four boundaries (first <i>and</i> second exon start/end) within ±50 bp, a "
          "different second exon being a distinct event; <b>A3SS / A5SS</b> — exact "
          "identity of the long, short and flanking exon coordinates only (i.e. the "
          "JC / JCEC merge), so alternative sites a few nt apart are kept.", "body"),
        p("These steps reduce redundancy and low-confidence calls, yielding a curated "
          "set of splicing events that is used throughout the rest of the pipeline.", "body"),
    ]

    if {"a", "b"} & selected_sections:
        _n = _next_app_a()
        story += [
            p(f"<b>{_n}. Splicing Event Detection — rMATS</b>", "h3"),
            p("Alternative splicing events (SE, RI, A3SS, A5SS, MXE) are detected by "
              "<b>rMATS</b> (Shen et al., 2014 [1]) from aligned RNA-seq data. rMATS uses a "
              "likelihood-ratio test to assess whether the difference in mean ΔΨ between groups "
              "exceeds a user-defined threshold, while modelling replicate variability in a "
              "hierarchical framework. Junction and exon-body read counts are combined in the "
              "JCEC model, while JC mode uses junction reads only. "
              "Output files used here are junction counts (<i>.MATS.JC.txt</i>).", "body"),
        ]
        _n = _next_app_a()
        story += [
            p(f"<b>{_n}. Splice Site Annotation</b>", "h3"),
            p("For each SE event, rMATS-Viz extracts flanking genomic sequences from "
              "the GRCh38 (hg38) reference genome indexed with <b>samtools faidx</b>:", "body"),
            p("• <b>5'SS donor (skipped exon):</b> 3 nt exon + 6 nt intron (9 nt window)", "body"),
            p("• <b>3'SS acceptor (skipped exon):</b> 20 nt intron + 3 nt exon (23 nt window)", "body"),
            p("• <b>5'SS donor (upstream flanking exon):</b> 3 nt exon + 6 nt intron (9 nt window)", "body"),
            p("• <b>3'SS acceptor (downstream flanking exon):</b> 20 nt intron + 3 nt exon (23 nt window)", "body"),
            p("• <b>PPT:</b> ~47 nt upstream of the skipped exon acceptor site", "body"),
            p("The canonical GT-AG splice site rule (Shapiro &amp; Senapathy, 1987 [2]; "
              "Burge &amp; Karlin, 1997 [3]) is verified at the first two intronic positions "
              "of the 5'SS (GT at +1/+2) and last two of the 3'SS (AG at -2/-1); when a window "
              "is truncated (contig end) the site is reported as unknown and excluded from the "
              "canonical-rate denominators. "
              "The PPT score is the fraction of pyrimidine nucleotides (C, T) in the PPT "
              "window. The branch point is searched with the yUnAy / YNYURAY heuristic "
              "(Coolidge et al., 1997 [4]; Gao et al., 2008): 7-mer candidates are scored "
              "0–7, the branch adenosine (position 6 of the 7-mer) is mandatory, and only "
              "candidates whose branch A lies 18–44 nt upstream of the exon start are "
              "considered (&gt; 95 % of human branch points, Leman et al., 2020). The reported "
              "branch-point distance is measured from the branch adenosine to the exon start "
              "(3'SS AG), and the matched 7-mer and its position are stored.", "body"),
        ]
        _n = _next_app_a()
        story += [
            p(f"<b>{_n}. Sequence Logos</b>", "h3"),
            p("Position weight matrices (PWMs) are computed from all extracted "
              "sequences per group. Logos are displayed in <b>frequency mode</b>: "
              "every column fills the full logo height, and the height of each letter "
              "is proportional to the raw nucleotide frequency f(b,i) at that position. "
              "No information-content (bits) scaling is applied, making each column "
              "directly comparable across positions regardless of conservation level. "
              "Canonical splice-site positions (GT at +1/+2 for donor; AG at -2/-1 for "
              "acceptor) are highlighted in yellow.", "body"),
        ]
        _n = _next_app_a()
        story += [
            p(f"<b>{_n}. Reading Frame Classification</b>", "h3"),
            p("The skipped exon is classified by reading-frame impact using the "
              "MANE Select transcript (Morales et al., 2022 [5]) when available:", "body"),
            p("• <b>in_frame:</b> CDS length divisible by 3 — protein domain loss without frameshift", "body"),
            p("• <b>frameshift:</b> CDS length not divisible by 3 — may lead to a truncated protein. "
              "<i>Note:</i> frameshift does not imply nonsense-mediated decay (NMD); NMD depends on "
              "the position of the premature termination codon (PTC) relative to the last exon-exon "
              "junction (&gt;50 nt upstream rule). Experimental validation is required to confirm NMD.", "body"),
            p("• <b>non_coding:</b> exon entirely within UTR — regulatory impact", "body"),
            p("• <b>unknown:</b> no MANE annotation available — such events are reported "
              "separately and excluded from the denominator of all frame percentages.", "body"),
        ]
        _n = _next_app_a()
        story += [
            p(f"<b>{_n}. MANE Select Annotation</b>", "h3"),
            p("The MANE Select transcript is identified from a local GFF3 file "
              "(MANE.GRCh38.ensembl_genomic.gff.gz) when available, or via the Ensembl "
              "REST API (Cunningham et al., 2022 [6]) as fallback. The skipped exon is "
              "mapped to transcript coordinates to determine exon rank, CDS overlap, and "
              "frame impact. Results are cached in a local SQLite database.", "body"),
            p(f"<b>{_n}b. MANE Exon Boundary Correction</b>", "h3"),
            p("rMATS exon coordinates come from the alignment annotation (GTF) and may "
              "differ from MANE Select transcript boundaries, causing splice-site "
              "sequences to be extracted at incorrect genomic positions. To correct this, "
              "the MANE exon is matched by reciprocal overlap (≥ 50%). When overlap "
              "matching fails, a flanking-based fallback identifies the consensual "
              "skipped exon as the MANE exon located between the upstream and downstream "
              "flanking exon boundaries (derived from junction reads). Events corrected "
              "via the flanking fallback are listed in the report.", "body"),
        ]

    if is_deep and "c" in selected_sections:
        _n = _next_app_a()
        _tests_a = (comparison or {}).get("statistical_tests", []) if comparison else []
        _n_tests_a = len(_tests_a)
        _n_welch = sum(1 for t in _tests_a if t.get("test_name") == "Welch's t-test")
        _n_mwu = sum(1 for t in _tests_a if t.get("test_name") == "mann_whitney_u")
        _n_z = sum(1 for t in _tests_a if t.get("test_name") == "Proportion z-test")
        _pv_txt = (
            f", p ≤ {deep_analysis.pvalue_threshold}"
            if getattr(deep_analysis, "pvalue_threshold", None) is not None else ""
        )
        story += [
            p(f"<b>{_n}. Deep Analysis</b>", "h3"),
            p(f"Events are classified as <b>significant</b> (FDR ≤ {deep_analysis.fdr_threshold}, "
              f"|ΔΨ| ≥ {deep_analysis.delta_psi_min}{_pv_txt}) or <b>non-significant</b> (all others). "
              "Splice features are compared between the two groups using:", "body"),
            p(f"• <b>Welch's t-test</b> (unequal variances, two-tailed; {_n_welch} tests): mean ΔΨ, "
              "exon size, PPT score, PPT T content, PPT C content, upstream and downstream intron size", "body"),
            p(f"• <b>Mann-Whitney U test</b> (rank-based, two-tailed, tie-corrected normal approximation; "
              f"{_n_mwu} tests): the same continuous features, robust to their right-skewed distributions", "body"),
            p(f"• <b>Two-proportion z-test</b> (two-tailed, pooled; {_n_z} tests): canonical GT/AG rates "
              "(skipped exon and flanking exons), in-frame proportion (known frames only), "
              "branch-point detection rate; ≥ 5 events per group required", "body"),
            p("Welch-Satterthwaite degrees of freedom are used for the t-distribution. "
              f"The panel comprises {_n_tests_a} tests; raw p-values are reported together with "
              "Benjamini-Hochberg adjusted q-values computed across the whole panel. The "
              "significance stars in the figures use the raw p &lt; 0.05 criterion; the "
              "comparison table flags q &lt; 0.05 with a dagger (†).", "body"),
        ]

    if is_deep and "d" in selected_sections:
        _n = _next_app_a()
        _perm_exact_only = bool(permutation_table) and all(pt.get("label") for pt in permutation_table)
        story += [
            p(f"<b>{_n}. Permutation Test</b>", "h3"),
            p("For each significant SE event, sample labels are permuted (keeping group sizes "
              "fixed) to build a null distribution of ΔΨ. When the number of distinct label "
              "splits N = C(n1+n2, n1) is ≤ 5000, all splits are enumerated and the exact "
              "two-tailed p-value is p = r / N, where r is the number of splits whose |ΔΨ| is ≥ "
              "the observed |ΔΨ| (the observed labelling is one of them, so p ≥ 1/N). Otherwise "
              "K random permutations are drawn and p = (r + 1) / (K + 1); the +1 correction avoids "
              "p = 0 (Phipson &amp; Smyth, 2010 [7]). The Monte-Carlo test is run at "
              "K = 50/100/250/500 iterations to assess convergence unless all events were "
              "enumerated exactly"
              + (" (the case here: a single exact-enumeration row is reported)" if _perm_exact_only else "")
              + ", and the minimum attainable p-value given the replicate design is "
              "reported.", "body"),
        ]

    if is_deep and "e" in selected_sections:
        _n = _next_app_a()
        _hn_n_regions = len(_heatmap_region_order(hnrnp_data or {}))
        _hn_n_results = len((hnrnp_data or {}).get("results", []))
        story += [
            p(f"<b>{_n}. hnRNP Motif Enrichment Analysis</b>", "h3"),
            p("RNA-binding protein (RBP) motif enrichment is computed in a rMAPS2-inspired "
              f"framework (Hwang et al., 2020 [11]). For each SE event {_hn_n_regions} regions are "
              "extracted from GRCh38 (samtools faidx), following the rMAPS2 design of scanning "
              "both ends of each flanking intron: (1) upstream exon (up to 250 nt adjacent to the "
              "intron), (2) upstream intron, 5'SS side (up to 250 nt after the 6-nt 5'SS signal), "
              "(3) upstream intron, 3'SS side (up to 250 nt before the 20-nt 3'SS consensus zone, "
              "i.e. the PPT / PTB / hnRNP C territory immediately upstream of the skipped exon), "
              "(4) skipped exon (full sequence), (5) downstream intron, 5'SS side (up to 250 nt "
              "after the 6-nt 5'SS signal of the skipped exon), (6) downstream intron, 3'SS side "
              "(up to 250 nt before the 20-nt 3'SS zone of the downstream exon), and (7) downstream "
              "exon (up to 250 nt). Minus-strand events are reverse-complemented before scanning. "
              "Each window is clipped to the intron body minus the exclusion zones, so in introns "
              "shorter than 526 nt the 5'SS-side and 3'SS-side windows of the same intron overlap "
              "(the shared nucleotides are scanned in both windows, as in rMAPS2, and the two "
              "windows are not independent tests); after the exclusion zones (6 nt + 20 nt = "
              "26 nt) an intron ≤ 26 nt yields no intronic sequence. Such events are excluded from the corresponding intronic "
              "region only (they still contribute to the exonic regions), consistently with "
              "rMAPS2; the N reported per cell reflects the events that actually contributed "
              "sequence for that region.", "body"),
            p("Nineteen consensus motifs for eight protein families (hnRNP A1/A2, E (PCBP1/E1 "
              "and PCBP2/E2), F/H, K, C, L, M, PTB/I) are matched using IUPAC-degenerate pattern "
              "search derived from CISBP-RNA (Ray et al., 2013 [12]), Martinez-Contreras et al. "
              "(2006 [13]), and for hnRNP E (PCBP1/E1 CCWWHCC = CC[AT][AT][ACT]CC; PCBP2/E2 CCYYCCH = "
              "CC[CT][CT]CC[ACT], both from rMAPS2 Supplementary Table S2, Homo sapiens): "
              "Chkheidze et al. (1999 [14]) and Makeyev &amp; Liebhaber (2002 [15]). "
              "For each motif-region pair two statistics are computed between the significant and "
              "background groups: (a) the <b>presence</b> rate (fraction of events with ≥ 1 match) "
              "with a pooled two-proportion z-test, and (b) the per-event motif <b>density</b> "
              "(matched nucleotides / region length) with a Mann-Whitney U test, which keeps its "
              "power when short motifs (AGG, GGG, UUUU, CUCU…) are present in nearly every 250-nt "
              "region. Benjamini-Hochberg FDR correction is applied separately to each family of "
              f"p-values across all {_hn_n_results} tested (motif × region) pairs; associations "
              "with q &lt; 0.05 are reported as significant. rMAPS2 instead uses a Wilcoxon "
              "rank-sum test on 50-nt sliding-window densities.", "body"),
            p("<b>Summary — SpliceAnalyzer vs. rMAPS2:</b> rMAPS2 characterises positional RBP "
              "binding preferences through nucleotide-resolution sliding-window density plots and "
              "rank-based non-parametric statistics, making it well-suited for visualising where "
              "along a splicing window a motif is enriched. SpliceAnalyzer adopts a region-centric "
              f"model: each of the {_hn_n_regions} predefined genomic sub-regions is treated as a "
              "unit, presence rates are compared with a two-proportion z-test and per-event "
              "densities with a Mann-Whitney U test, and false discovery rate control is applied "
              "with Benjamini-Hochberg correction across all motif–region pairs. This design "
              "trades positional resolution for statistical clarity and direct interpretability in "
              "the context of discrete regulatory zones (exonic body, 5'SS-proximal and "
              "3'SS-proximal intronic windows), providing a complementary, region-level view of "
              "hnRNP motif associations.", "body"),
            p(f"<b>{_n}b. Regulatory Effect Annotations</b>", "h3"),
            p("The heatmap displays the established regulatory effect (ESE, ESS, ISE, ISS) "
              "for each protein × region pair when supported by strong published evidence. "
              "Silencer annotations (ESS/ISS, orange frame) and enhancer annotations "
              "(ESE/ISE, green frame) are derived from the following peer-reviewed sources:", "body"),
            p("Annotations are given per protein family and intron/exon; for the two windows "
              "of the same intron (5'SS side and 3'SS side) the same intronic assignment applies "
              "unless stated otherwise.", "body"),
            p("• <b>hnRNP A1/A2:</b> ESS in exons, ISS in introns — "
              "Zhu et al. 2001 [16]; Damgaard et al. 2002 [17]; Kashima et al. 2007 [18]", "body"),
            p("• <b>hnRNP F/H:</b> ESS in exons, ISE in downstream intron — "
              "Martinez-Contreras et al. 2006 [13]; Chen et al. 1999 [19]; Erkelenz et al. 2013 [20]", "body"),
            p("• <b>hnRNP C:</b> ESS in skipped exon, ISE in upstream intron — "
              "König et al. 2010 [21]; Zarnack et al. 2013 [22]", "body"),
            p("• <b>hnRNP L:</b> ESS in skipped exon — "
              "House &amp; Lynch 2006 [23]; Hui et al. 2005 [24]", "body"),
            p("• <b>hnRNP M:</b> ESS in skipped exon, ISS in downstream intron — "
              "Huelga et al. 2012 [25]", "body"),
            p("• <b>PTB (hnRNP I):</b> ESS in skipped exon, ISS in flanking introns — "
              "Xue et al. 2009 [26]; Wagner &amp; Garcia-Blanco 2001 [27]", "body"),
            p("• <b>PCBP1, PCBP2, hnRNP K:</b> no assignment — insufficient position-specific "
              "splicing data; primarily characterised for mRNA stability and translational control.", "body"),
            p("Assignments are conservative: protein × region pairs with context-dependent or "
              "insufficiently replicated effects are left unannotated (no frame). "
              "The general principle that hnRNPs tend to silence from exonic positions and can "
              "enhance or silence from intronic positions depending on the protein is supported "
              "by genome-wide RNA splicing maps (Witten &amp; Ule, 2011 [28]).", "body"),
        ]

    if is_deep and "f" in selected_sections:
        _n = _next_app_a()
        story += [
            p(f"<b>{_n}. Pathway Enrichment (Enrichr)</b>", "h3"),
            p("Unique HGNC gene symbols derived from significant splicing events are submitted to "
              "the Enrichr REST API (Ma'ayan Lab; Chen et al., 2013 [8]; Kuleshov et al., 2016 "
              "[9]; Xie et al., 2021 [10]) via a POST request to <i>/addList</i>. Enrichment is retrieved for five "
              "curated gene-set libraries: KEGG 2021 Human, GO Biological Process 2023, GO "
              "Molecular Function 2023, Reactome 2022, and WikiPathways 2023 Human.", "body"),
            p("For each term the Enrichr combined score is defined as: "
              "CS = log(p) × z, where p is the unadjusted Fisher's exact test p-value for overlap "
              "and z is Enrichr's deviation-from-expected-rank z-score. "
              "Adjusted p-values are reported separately by Enrichr within each library. "
              "The top 10 terms per library by adjusted p-value are "
              "retained and displayed in this report.", "body"),
        ]

    story.append(sp())

    # ── Appendix B — References ──────────────────────────────────────────────
    # [1]–[10] are always emitted (cited by the default report).
    # [11]–[28] cover the hnRNP enrichment panel and are appended only when
    # section "e" is included (is_deep and "e" in selected_sections).
    #  [1] Shen 2014       [2] Shapiro 1987    [3] Burge 1997
    #  [4] Coolidge 1997   [5] Morales 2022    [6] Cunningham 2022
    #  [7] Phipson 2010    [8] Chen 2013       [9] Kuleshov 2016
    #  [10] Xie 2021
    # hnRNP-conditional:
    #  [11] Hwang 2020         [12] Ray 2013          [13] Martinez-Contreras 2006
    #  [14] Chkheidze 1999     [15] Makeyev 2002      [16] Zhu 2001
    #  [17] Damgaard 2002      [18] Kashima 2007      [19] Chen CD 1999
    #  [20] Erkelenz 2013      [21] König 2010        [22] Zarnack 2013
    #  [23] House 2006         [24] Hui 2005          [25] Huelga 2012
    #  [26] Xue 2009           [27] Wagner 2001       [28] Witten 2011
    story.append(PageBreak())
    story += [
        p("Appendix B — Bibliographic References", "h2"),
        hr(),
        p("[1] Shen S et al. <i>rMATS: robust and flexible detection of differential "
          "alternative splicing from replicate RNA-Seq data.</i> PNAS. 2014;111(51):E5593-E5601.", "body"),
        p("[2] Shapiro MB, Senapathy P. <i>RNA splice junctions of different classes "
          "of eukaryotes: sequence statistics and functional implications in gene "
          "expression.</i> Nucleic Acids Res. 1987;15(17):7155-7174.", "body"),
        p("[3] Burge C, Karlin S. <i>Prediction of complete gene structures in human "
          "genomic DNA.</i> J Mol Biol. 1997;268(1):78-94.", "body"),
        p("[4] Coolidge CJ, Seely RJ, Patton JG. <i>Functional analysis of the "
          "polypyrimidine tract in pre-mRNA splicing.</i> Nucleic Acids Res. "
          "1997;25(4):888-896.", "body"),
        p("[5] Morales J et al. <i>A joint NCBI and EMBL-EBI transcript set for "
          "clinical genomics and research.</i> Nature. 2022;604:310-315.", "body"),
        p("[6] Cunningham F et al. <i>Ensembl 2022.</i> Nucleic Acids Res. "
          "2022;50(D1):D988-D995.", "body"),
        p("[7] Phipson B, Smyth GK. <i>Permutation P-values should never be zero: "
          "calculating exact P-values when permutations are randomly drawn.</i> "
          "Stat Appl Genet Mol Biol. 2010;9(1):Article 39.", "body"),
        p("[8] Chen EY, Tan CM, Kou Y, Duan Q, Wang Z, Meirelles GV, Clark NR, "
          "Ma'ayan A. <i>Enrichr: interactive and collaborative HTML5 gene list "
          "enrichment analysis tool.</i> BMC Bioinformatics. 2013;14:128.", "body"),
        p("[9] Kuleshov MV, Jones MR, Rouillard AD, Fernandez NF, Duan Q, Wang Z, "
          "Koplev S, Jenkins SL, Jagodnik KM, Lachmann A, McDermott MG, Monteiro CD, "
          "Gundersen GW, Ma'ayan A. <i>Enrichr: a comprehensive gene set enrichment "
          "analysis web server 2016 update.</i> Nucleic Acids Res. 2016;44(W1):W90-W97.", "body"),
        p("[10] Xie Z, Bailey A, Kuleshov MV, Clarke DJB, Evangelista JE, Jenkins SL, "
          "Lachmann A, Wojciechowicz ML, Kropiwnicki E, Jagodnik KM, Jeon M, Ma'ayan A. "
          "<i>Gene set knowledge discovery with Enrichr.</i> Curr Protoc. 2021;1(3):e90.", "body"),
    ]

    # hnRNP-only references — included only when the hnRNP section is rendered.
    if is_deep and "e" in selected_sections:
        story += [
            p("[11] Hwang JY, Jung S, Kook TL, Rouchka EC, Bok J, Park JW. "
              "<i>rMAPS2: An update of the RNA map analysis and plotting server for "
              "alternative splicing regulation.</i> Nucleic Acids Res. 2020;48(W1):W300-W306.", "body"),
            p("[12] Ray D, Kazan H, Cook KB, Weirauch MT, Najafabadi HS, Li X et al. "
              "<i>A compendium of RNA-binding motifs for decoding gene regulation.</i> "
              "Nature. 2013;499(7457):172-177.", "body"),
            p("[13] Martinez-Contreras R, Cloutier P, Shkreta L, Fisette JF, Revil T, Chabot B. "
              "<i>hnRNP proteins and splicing control.</i> Adv Exp Med Biol. 2007;623:123-147.", "body"),
            p("[14] Chkheidze AN, Lyakhov DL, Makeyev AV, Morales J, Kong J, Liebhaber SA. "
              "<i>Assembly of the alpha-globin mRNA stability complex reflects binary "
              "interaction between the pyrimidine-rich 3' untranslated region determinant "
              "and poly(C) binding protein alphaCP.</i> Mol Cell Biol. 1999;19(7):4572-4581.", "body"),
            p("[15] Makeyev AV, Liebhaber SA. "
              "<i>The poly(C)-binding proteins: a multiplicity of functions and a search "
              "for mechanisms.</i> RNA. 2002;8(3):265-278.", "body"),
            p("[16] Zhu J, Mayeda A, Krainer AR. <i>Exon identity established through "
              "differential antagonism between exonic splicing silencer-bound hnRNP A1 and "
              "enhancer-bound SR proteins.</i> Mol Cell. 2001;8(6):1351-1361.", "body"),
            p("[17] Damgaard CK, Tange TØ, Kjems J. <i>hnRNP A1 controls HIV-1 mRNA "
              "splicing through cooperative binding to intron and exon splicing silencers "
              "in the context of a conserved secondary structure.</i> RNA. 2002;8(11):1401-1415.", "body"),
            p("[18] Kashima T, Rao N, David CJ, Manley JL. <i>hnRNP A1 functions with "
              "specificity in repression of SMN2 exon 7 splicing.</i> Hum Mol Genet. "
              "2007;16(24):3149-3159.", "body"),
            p("[19] Chen CD, Kobayashi R, Helfman DM. <i>Binding of hnRNP H to an exonic "
              "splicing silencer is involved in the regulation of alternative splicing "
              "of the rat β-tropomyosin gene.</i> Genes Dev. 1999;13(5):593-606.", "body"),
            p("[20] Erkelenz S, Mueller WF, Evans MS, Busch A, Schöneweis K, Hertel KJ, "
              "Schaal H. <i>Position-dependent splicing activation and repression by SR "
              "and hnRNP proteins rely on common mechanisms.</i> RNA. 2013;19(1):96-102.", "body"),
            p("[21] König J, Zarnack K, Rot G, Curk T, Kayikci M, Zupan B, Turner DJ, "
              "Luscombe NM, Ule J. <i>iCLIP reveals the function of hnRNP particles in "
              "splicing at individual nucleotide resolution.</i> Nat Struct Mol Biol. "
              "2010;17(7):909-915.", "body"),
            p("[22] Zarnack K, König J, Tajnik M, Martincorena I, Eustermann S, Stévant I, "
              "Reyes A, Anders S, Luscombe NM, Ule J. <i>Direct competition between hnRNP C "
              "and U2AF65 protects the transcriptome from the exonization of Alu elements.</i> "
              "Cell. 2013;152(3):453-466.", "body"),
            p("[23] House AE, Lynch KW. <i>An exonic splicing silencer represses spliceosome "
              "assembly after ATP-dependent exon recognition.</i> Nat Struct Mol Biol. "
              "2006;13(10):937-944.", "body"),
            p("[24] Hui J, Hung LH, Heiner M, Schreiner S, Neumüller N, Reither G, Haas SA, Bindereif A. "
              "<i>Intronic CA-repeat and CA-rich elements: a new class of regulators of "
              "mammalian alternative splicing.</i> EMBO J. 2005;24(11):1988-1998.", "body"),
            p("[25] Huelga SC, Vu AQ, Arnold JD, Liang TY, Liu PP, Yan BY, Donohue JP, "
              "Shiue L, Hoon S, Brenner S, Ares M Jr, Yeo GW. <i>Integrative genome-wide "
              "analysis reveals cooperative regulation of alternative splicing by hnRNP "
              "proteins.</i> Cell Rep. 2012;1(2):167-178.", "body"),
            p("[26] Xue Y, Zhou Y, Wu T, Zhu T, Ji X, Kwon YS, Zhang C, Yeo G, Black DL, "
              "Sun H, Fu XD, Zhang Y. <i>Genome-wide analysis of PTB-RNA interactions "
              "reveals a strategy used by the general splicing repressor to modulate exon "
              "inclusion or skipping.</i> Mol Cell. 2009;36(6):996-1006.", "body"),
            p("[27] Wagner EJ, Garcia-Blanco MA. <i>Polypyrimidine tract binding protein "
              "antagonizes exon definition.</i> Mol Cell Biol. 2001;21(10):3281-3288.", "body"),
            p("[28] Witten JT, Ule J. <i>Understanding splicing regulation through RNA "
              "splicing maps.</i> Trends Genet. 2011;27(3):89-97.", "body"),
        ]

    story.append(sp())

    # ── Appendix C — Statistical Methods ────────────────────────────────────
    # Same mapping logic as Appendix A:
    # C.1-C.3: always include if section A or B selected
    # C.4 (Deep Analysis tests): include if section C selected
    # C.5 (Permutation): include if section D selected
    # C.6 (hnRNP): include if section E selected
    # C.7 (Enrichr): include if section F selected
    _app_c_n = [0]

    def _next_app_c() -> int:
        _app_c_n[0] += 1
        return _app_c_n[0]

    story.append(PageBreak())
    story += [
        p("Appendix C — Statistical Methods", "h2"),
        hr(),
    ]

    if {"a", "b"} & selected_sections:
        _cn = _next_app_c()
        story += [
            p(f"<b>C.{_cn} Splicing Event Statistics (rMATS)</b>", "h3"),
            p("rMATS computes for each event:", "body"),
            p("• <b>ΔΨ (delta-PSI)</b>: ΔΨ = PSI<sub>sample1</sub> − PSI<sub>sample2</sub>, "
              "where PSI is the percent spliced in. Range: [−1, +1].", "body"),
            p("• <b>p-value</b>: rMATS uses a likelihood-ratio test to assess whether "
              "the difference in mean PSI between groups exceeds a user-defined threshold c, "
              "while modelling replicate variability in a hierarchical framework.", "body"),
            p("• <b>FDR</b>: Benjamini-Hochberg correction across all events.", "body"),
        ]
        _cn = _next_app_c()
        story += [
            p(f"<b>C.{_cn} Sequence Logos</b>", "h3"),
            p("Logos are rendered in <b>frequency mode</b>: every column fills the full "
              "logo height and the height of each letter at position i is:", "body"),
            p("&nbsp;&nbsp;&nbsp;height(b,i) = f(b,i) × H<sub>logo</sub>", "code"),
            p("where f(b,i) is the raw nucleotide frequency of base b at position i "
              "and H<sub>logo</sub> is the fixed column height. No information-content "
              "(bits) scaling or small-sample correction is applied. This makes every "
              "column directly comparable and matches the frequency view in the web "
              "application. Base colours: A = green, C = blue, G = orange, T = red.", "body"),
        ]
        _cn = _next_app_c()
        story += [
            p(f"<b>C.{_cn} PPT Score</b>", "h3"),
            p("The polypyrimidine tract (PPT) score is the fraction of pyrimidine "
              "nucleotides (C, T) in the ~47 nt window upstream of the acceptor site. "
              "Individual T content and C content are also reported as the fraction of "
              "thymine and cytosine bases respectively in the same window. "
              "The branch point is detected with the yUnAy / YNYURAY heuristic within the "
              "PPT window (Coolidge et al., 1997; Gao et al., 2008): each 7-mer is scored "
              "0–7 for agreement with the consensus, the branch adenosine is mandatory, and "
              "only candidates whose branch A lies 18–44 nt upstream of the exon start are "
              "retained; the best-scoring candidate (score ≥ 5) is reported with its distance "
              "measured from the branch A to the exon start.", "body"),
        ]

    if is_deep and "c" in selected_sections:
        _cn = _next_app_c()
        story += [
            p(f"<b>C.{_cn} Deep Analysis Statistical Tests</b>", "h3"),
            p("Events are split into significant and non-significant groups. "
              "The following two-tailed tests compare splice features:", "body"),
            p("• <b>Welch's t-test</b>: for continuous features (mean ΔΨ, exon size, "
              "PPT score, PPT T content, PPT C content). Uses Welch-Satterthwaite approximation for degrees of freedom:", "body"),
            p("&nbsp;&nbsp;&nbsp;df = (s<sub>1</sub><super>2</super>/n<sub>1</sub> + s<sub>2</sub><super>2</super>/n<sub>2</sub>)<super>2</super> "
              "/ [(s<sub>1</sub><super>2</super>/n<sub>1</sub>)<super>2</super>/(n<sub>1</sub>-1) "
              "+ (s<sub>2</sub><super>2</super>/n<sub>2</sub>)<super>2</super>/(n<sub>2</sub>-1)]", "code"),
            p("• <b>Mann-Whitney U test</b>: for the same continuous features, as a "
              "distribution-free companion to Welch's test. Values of both groups are pooled and "
              "mid-ranked; U<sub>1</sub> = R<sub>1</sub> − n<sub>1</sub>(n<sub>1</sub>+1)/2 and "
              "the two-tailed p-value uses the normal approximation with tie correction and a "
              "0.5 continuity correction:", "body"),
            p("&nbsp;&nbsp;&nbsp;z = (U<sub>1</sub> − n<sub>1</sub>n<sub>2</sub>/2 ∓ 0.5) / "
              "sqrt[ n<sub>1</sub>n<sub>2</sub>/12 × ((N+1) − Σ(t<super>3</super> − t)/(N(N−1))) ]", "code"),
            p("• <b>Two-proportion z-test</b>: for proportions (canonical GT, canonical AG, "
              "upstream GT, downstream AG, in-frame % of known frames, branch-point detection). "
              "This is a large-sample normal approximation, not an exact test; ≥ 5 events per "
              "group are required, otherwise the test is not run:", "body"),
            p("&nbsp;&nbsp;&nbsp;z = (p<sub>1</sub> - p<sub>2</sub>) "
              "/ sqrt[p(1-p)(1/n<sub>1</sub> + 1/n<sub>2</sub>)]", "code"),
            p("where p is the pooled proportion across both groups. "
              "Two-tailed p-values are computed from the normal CDF via the exact identity "
              "Φ(x) = 0.5 × erfc(−x / √2).", "body"),
            p("All p-values are two-tailed. The numerically evaluated regularized incomplete "
              "beta function (Lentz's continued-fraction algorithm) is used to evaluate the "
              "t-distribution upper-tail probability P(T ≥ |t|). "
              "Multiple testing: Benjamini-Hochberg q-values are computed across the whole "
              f"panel ({len((comparison or {}).get('statistical_tests', []))} tests, "
              "m = number of evaluable tests):", "body"),
            p("&nbsp;&nbsp;&nbsp;q<sub>(i)</sub> = min<sub>j ≥ i</sub> ( m · p<sub>(j)</sub> / j )", "code"),
            p("Raw p &lt; 0.05 (★) is reported for continuity with the interactive view; "
              "q &lt; 0.05 (†) controls the expected false discovery rate at 5 % across the "
              "panel and is the criterion to prefer when several features are examined.", "body"),
        ]

    if is_deep and "d" in selected_sections:
        _cn = _next_app_c()
        _perm_exact_only_c = bool(permutation_table) and all(pt.get("label") for pt in permutation_table)
        story += [
            p(f"<b>C.{_cn} Permutation Test</b>", "h3"),
            p("For each significant SE event, sample-label permutation generates a null ΔΨ "
              "distribution.  With n<sub>1</sub> and n<sub>2</sub> replicates per group there are "
              "N = C(n<sub>1</sub>+n<sub>2</sub>, n<sub>1</sub>) distinct label splits.  When N ≤ 5000 "
              "all splits are enumerated and the p-value is exact:", "body"),
            p("&nbsp;&nbsp;&nbsp;p = r / N &nbsp;&nbsp;(r = number of splits with |ΔΨ*| ≥ |ΔΨ<sub>obs</sub>|, "
              "including the observed one)", "code"),
            p("Otherwise K random permutations are drawn (Monte-Carlo) and", "body"),
            p("&nbsp;&nbsp;&nbsp;p = (r + 1) / (K + 1)", "code"),
            p("where the +1 correction avoids p = 0 (Phipson &amp; Smyth, 2010 [7]).  "
              "The Monte-Carlo test is run at K = 50/100/250/500 iterations to demonstrate "
              "convergence unless all events were enumerated exactly"
              + (" (the case here: a single exact-enumeration row is reported)" if _perm_exact_only_c else "")
              + ".  The smallest attainable p-value is 1/N for exact enumeration "
              "(e.g. 0.05 with 3 vs 3 replicates, N = 20; 0.167 with 2 vs 2, N = 6) and "
              "1/(K+1) for Monte-Carlo sampling; it is reported in the permutation section and "
              "must be considered when reading the fraction of events below 0.05 or 0.01.", "body"),
        ]

    if is_deep and "e" in selected_sections:
        _cn = _next_app_c()
        story += [
            p(f"<b>C.{_cn} hnRNP Motif Enrichment — Presence z-Test and Density Mann-Whitney Test</b>", "h3"),
            p("<b>(a) Presence.</b> For each motif m in region r, let p^<sub>1</sub> = x<sub>1</sub> / n<sub>1</sub> "
              "and p^<sub>2</sub> = x<sub>2</sub> / n<sub>2</sub> be the hit rates "
              "in the significant and background groups respectively. "
              "The pooled proportion is p^ = (x<sub>1</sub> + x<sub>2</sub>) / "
              "(n<sub>1</sub> + n<sub>2</sub>). "
              "The test statistic is:", "body"),
            p("&nbsp;&nbsp;&nbsp;z = (p^<sub>1</sub> - p^<sub>2</sub>) / "
              "sqrt[ p^(1 - p^)(1/n<sub>1</sub> + 1/n<sub>2</sub>) ]", "code"),
            p("Two-tailed p-values are computed from the normal CDF via the exact identity "
              "Φ(x) = 0.5 × erfc(−x / √2); note that the two-proportion z-test itself is "
              "a large-sample normal approximation, not an exact test. "
              "It is applied only when group sizes are sufficient for stable proportion "
              "estimates: ≥ 5 events per group are required, otherwise the pair is not tested.", "body"),
            p("<b>(b) Density.</b> For every event the motif density d = (matched nucleotides) / "
              "(region length) is computed; the densities of the significant and background "
              "groups are compared with a two-sided Mann-Whitney U test (mid-ranks, tie-corrected "
              "normal approximation, ≥ 5 events per group). Unlike the presence test, this "
              "statistic does not saturate when a short motif occurs in almost every region.", "body"),
            p("Raw p-values of each test are adjusted separately across all testable (motif × "
              "region) pairs using the Benjamini-Hochberg FDR procedure as a discovery-oriented "
              "screen (q &lt; 0.05); the report table lists both q-values.", "body"),
        ]

    if is_deep and "f" in selected_sections:
        _cn = _next_app_c()
        story += [
            p(f"<b>C.{_cn} Enrichr Combined Score</b>", "h3"),
            p("The Enrichr combined score (Chen et al., 2013 [8]) is defined as:", "body"),
            p("&nbsp;&nbsp;&nbsp;CS = log(p) × z", "code"),
            p("where log is the natural logarithm, p is the unadjusted Fisher's exact test "
              "p-value for overlap between the submitted gene list and the gene set, and z is "
              "Enrichr's deviation-from-expected-rank z-score. Adjusted p-values are reported "
              "separately by Enrichr within each library.", "body"),
        ]

    story.append(sp())

    # ── Closing note: tool availability ─────────────────────────────────────
    story += [
        hr(),
        p(
            "<i>SpliceAnalyzer — the tool used to generate this report — is "
            "open-source and freely available at "
            "<font color='#2563eb'>https://github.com/wallideb/SpliceAnalyzer</font>, "
            "together with full documentation and a detailed description of the "
            "methodology summarised in this report.</i>",
            "small",
        ),
    ]

    doc.build(story)
    return buf.getvalue()


_ALL_SECTIONS = {"a", "b", "c", "d", "e", "f", "top_events"}


def _parse_sections(sections_param: str | None) -> set[str]:
    """Parse comma-separated section keys into a set.  Returns all sections if None."""
    if not sections_param:
        return set(_ALL_SECTIONS)
    return {s.strip().lower() for s in sections_param.split(",") if s.strip().lower() in _ALL_SECTIONS}


@router.get("/{analysis_id}/pdf")
async def export_analysis_pdf(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    sections: str | None = None,
) -> StreamingResponse:
    """Generate a PDF analysis report for *analysis_id* (all events)."""

    selected = _parse_sections(sections)
    await _assert_splice_features_ready(db, analysis_id)
    analysis, group1_label, group2_label = await _get_analysis_with_groups(db, analysis_id)
    events, features = await _load_events_and_features(db, analysis_id)

    pdf_bytes = await asyncio.to_thread(
        _build_pdf, analysis, events, features, group1_label, group2_label,
        selected_sections=selected,
    )

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
    sections: str | None = None,
) -> StreamingResponse:
    """Generate a PDF report scoped to a deep analysis (filtered events + comparison)."""
    selected = _parse_sections(sections)
    await _assert_splice_features_ready(db, analysis_id)

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

    comparison = None
    if "c" in selected:
        stat_tests = _compute_stat_tests(sig_events, sig_feats, nonsig_events, nonsig_feats)
        comparison = {
            "significant": _compute_group_stats(sig_events, sig_feats).model_dump(),
            "not_significant": _compute_group_stats(nonsig_events, nonsig_feats).model_dump(),
            "statistical_tests": [
                {"feature": t.feature, "test_name": t.test_name,
                 "statistic": t.statistic, "p_value": t.p_value,
                 "q_value": t.q_value, "significant": t.significant,
                 "significant_fdr": t.significant_fdr}
                for t in stat_tests
            ],
        }

    # ── hnRNP motif enrichment ────────────────────────────────────────────
    async def _compute_hnrnp() -> dict | None:
        """Run hnRNP motif enrichment on SE events; returns plain dict or None."""
        try:
            from app.services.hnrnp_motifs import (
                REGION_NAMES, build_se_regions, compare_groups, scan_group,
                REGULATORY_EFFECTS,
            )

            se_sig = [e for e in sig_events if e.event_type == "SE"]
            se_bg = [e for e in nonsig_events if e.event_type == "SE"]

            # Same region extraction as deep_analyses.get_hnrnp_motifs
            sig_regions, bg_regions = await asyncio.gather(
                asyncio.to_thread(build_se_regions, se_sig, None, "pdf-sig"),
                asyncio.to_thread(build_se_regions, se_bg, None, "pdf-bg"),
            )
            sig_scan, bg_scan = await asyncio.gather(
                asyncio.to_thread(scan_group, sig_regions),
                asyncio.to_thread(scan_group, bg_regions),
            )
            enrichment = await asyncio.to_thread(compare_groups, sig_scan, bg_scan)
            return {
                "n_sig_events": len(se_sig),
                "n_bg_events": len(se_bg),
                "regions": list(REGION_NAMES),
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
                        "density_u_stat": getattr(r, "density_u_stat", None),
                        "density_p_value": getattr(r, "density_p_value", None),
                        "density_p_adjusted": getattr(r, "density_p_adjusted", None),
                        "density_significant": bool(getattr(r, "density_significant", False)),
                        "regulatory_effect": REGULATORY_EFFECTS.get(r.protein, {}).get(r.region),
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

    # ── Permutation test (Monte-Carlo convergence table, seed 42) ───────
    # The report text states the test is run at 50, 100, 250 and 500 iterations
    # to assess convergence; the 500-iteration row is the reference used for
    # the summary (last row).  Exact enumeration (≤ 5000 label splits) is
    # independent of K, so when every event is enumerated exactly
    # (exact_fraction == 1.0) the 500-iteration run is reported as a single
    # "exact enumeration" row instead of four identical rows.
    from app.services.permutation import run_permutation

    _PERM_ITERATIONS = (50, 100, 250, 500)
    _PERM_REFERENCE_K = 500
    sig_features_list = [features.get(e.id) for e in sig_events]

    def _run_perm_table() -> list[dict]:
        def _row(k: int) -> dict:
            perm_res = run_permutation(
                sig_events,
                sig_features_list,
                n_iterations=k,
                only_se=True,
                seed=42,
            )
            return {
                "iterations": k,
                "label": None,
                "n_tested": perm_res.n_events_tested,
                "pct_p05": perm_res.pct_p05,
                "pct_p01": perm_res.pct_p01,
                "exact_fraction": getattr(perm_res, "exact_fraction", None),
                "min_p_attainable": getattr(perm_res, "min_p_attainable", None),
                "n_replicates_g1": getattr(perm_res, "n_replicates_g1", None),
                "n_replicates_g2": getattr(perm_res, "n_replicates_g2", None),
            }

        ref = _row(_PERM_REFERENCE_K)
        if ref.get("exact_fraction") == 1.0:
            ref["label"] = "exact enumeration (all label permutations)"
            return [ref]
        rows = [_row(k) for k in _PERM_ITERATIONS if k != _PERM_REFERENCE_K]
        rows.append(ref)  # reference row last
        return rows

    async def _compute_permutation() -> list[dict]:
        if not sig_events:
            return []
        return await asyncio.to_thread(_run_perm_table)

    # Run expensive analyses concurrently — only when their section is selected
    tasks: list = []
    task_keys: list[str] = []

    if "d" in selected:
        tasks.append(_compute_permutation())
        task_keys.append("d")
    if "e" in selected:
        tasks.append(_compute_hnrnp())
        task_keys.append("e")
    if "f" in selected:
        tasks.append(_compute_enrichr())
        task_keys.append("f")

    results = await asyncio.gather(*tasks) if tasks else []
    result_map = dict(zip(task_keys, results))

    permutation_table = result_map.get("d") or []
    hnrnp_data = result_map.get("e")
    enrichr_data = result_map.get("f")

    # Optional SVG side-dump of every figure (disabled unless SVG_EXPORT_DIR is set)
    svg_dir = (
        os.path.join(_settings.SVG_EXPORT_DIR, str(deep_analysis_id))
        if _settings.SVG_EXPORT_DIR else None
    )

    pdf_bytes = await asyncio.to_thread(
        _build_pdf, analysis, events, features, group1_label, group2_label,
        deep_analysis=deep, comparison=comparison,
        sig_map=sig_map, permutation_table=permutation_table,
        hnrnp_data=hnrnp_data, enrichr_data=enrichr_data,
        svg_dir=svg_dir, selected_sections=selected,
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_deep_{deep_analysis_id}.pdf"'
        },
    )
