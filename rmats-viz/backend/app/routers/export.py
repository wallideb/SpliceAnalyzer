from __future__ import annotations

import asyncio
import uuid
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
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
    stringdb  – highest STRING-DB combined score vs each analysis mutated gene
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
    analysis_q = await db.execute(
        select(Analysis).options(selectinload(Analysis.sample_groups)).where(Analysis.id == analysis_id)
    )
    analysis = analysis_q.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    g1 = next((g for g in analysis.sample_groups if g.group_index == 1), None)
    g2 = next((g for g in analysis.sample_groups if g.group_index == 2), None)
    group1_label = g1.group_label if g1 else "Group 1"
    group2_label = g2.group_label if g2 else "Group 2"

    # ── 2. Fetch all events ───────────────────────────────────────────────────
    result = await db.execute(
        select(SplicingEvent).where(SplicingEvent.analysis_id == analysis_id)
    )
    events: list[SplicingEvent] = list(result.scalars().all())

    # ── 3. Fetch SE splice features (keyed by event_id) ──────────────────────
    se_event_ids = [e.id for e in events if e.event_type == "SE"]
    features: dict[uuid.UUID, EventSpliceFeature] = {}
    if se_event_ids:
        feat_result = await db.execute(
            select(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(se_event_ids))
        )
        for feat in feat_result.scalars().all():
            features[feat.event_id] = feat

    # ── 4. Fetch external annotations (per unique gene symbol) ───────────────
    unique_symbols: list[str] = list({
        e.gene_symbol for e in events if e.gene_symbol
    })

    # PanelApp columns
    panelapp_data: dict[str, dict] = {}
    if "panelapp" in groups and unique_symbols:
        pa_results = await asyncio.gather(
            *[get_panels_for_gene(sym) for sym in unique_symbols],
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
            *[get_go_terms(sym, None) for sym in unique_symbols],
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
                    *[get_interaction(sym, mut) for sym, mut in pairs],
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

# ===========================================================================
# 3C — PDF Rapport d'analyse
# ===========================================================================

import statistics as _statistics
from datetime import date as _date

from reportlab.lib import colors as _colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4 as _A4
from reportlab.lib.styles import getSampleStyleSheet as _getStyles, ParagraphStyle
from reportlab.lib.units import cm as _cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF

_W, _H = _A4
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
        "center": ParagraphStyle(
            "Center", parent=base["Normal"],
            fontSize=9, alignment=TA_CENTER,
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


_FIG_NUM = 0


def _next_fig() -> int:
    global _FIG_NUM
    _FIG_NUM += 1
    return _FIG_NUM


# ---------------------------------------------------------------------------
# Figure builders (reportlab Drawings — resolution-independent vector)
# ---------------------------------------------------------------------------

def _fig_exon_size_histogram(exon_sizes: list[int]) -> Drawing | None:
    """Exon-size distribution histogram (25 nt bins)."""
    if not exon_sizes:
        return None

    import math as _math

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


def _fig_dpsi_distribution(events: list, group1_label: str = "Group 1", group2_label: str = "Group 2") -> Drawing | None:
    """ΔΨ distribution histogram for all events."""
    dpsi_vals = [e.inc_level_difference for e in events
                 if e.inc_level_difference is not None]
    if len(dpsi_vals) < 3:
        return None

    import math as _math

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


def _fig_splice_site_consensus(features_dict: dict, site: str = "donor") -> Drawing | None:
    """Simple PWM bar chart for donor (9 nt) or acceptor (23 nt) splice sites.

    Renders each position as stacked coloured bars (height ∝ freq × IC)
    following the sequence logo convention.
    """
    import math as _math
    from collections import Counter

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
    # Compute PWM
    pwm: list[dict[str, float]] = []
    for pos in range(seq_len):
        counts = Counter(seq[pos] for seq in sequences)
        total = sum(counts.values())
        freqs = {b: counts.get(b, 0) / total for b in "ACGT"}
        pwm.append(freqs)

    BASE_COLORS = {"A": "#22c55e", "C": "#3b82f6", "G": "#f97316", "T": "#ef4444"}

    COL_W = 22
    LOGO_H = 80  # max stack height = 2 bits
    MARGIN_L, MARGIN_B, MARGIN_T = 32, 24, 8
    W = MARGIN_L + seq_len * COL_W + 20
    H = MARGIN_T + LOGO_H + MARGIN_B

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_colors.HexColor("#fafafa"),
               strokeColor=_colors.HexColor("#e2e8f0"), strokeWidth=0.5))

    # Position labels — splice site convention
    if site == "donor":
        start_pos = -3
    else:
        start_pos = -20

    # Bits Y-axis
    for bit in [0, 1, 2]:
        y = MARGIN_B + (bit / 2) * LOGO_H
        d.add(Line(MARGIN_L - 3, y, MARGIN_L, y,
                    strokeColor=_colors.HexColor("#475569"), strokeWidth=0.5))
        d.add(String(MARGIN_L - 5, y - 2, str(bit),
                      fontSize=6, fontName="Helvetica", fillColor=_colors.HexColor("#475569"),
                      textAnchor="end"))
    d.add(Line(MARGIN_L, MARGIN_B, MARGIN_L, MARGIN_B + LOGO_H,
                strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8))

    # Y-axis label
    g = Group()
    g.transform = (0, 1, -1, 0, 10, MARGIN_B + LOGO_H / 2 - 10)
    g.add(String(0, 0, "bits", fontSize=7, fontName="Helvetica-Oblique",
                  fillColor=_colors.HexColor("#475569"), textAnchor="middle"))
    d.add(g)

    # Canonical positions to highlight
    if site == "donor":
        canonical = {1, 2}  # GT at +1, +2
    else:
        canonical = {-2, -1}  # AG at -2, -1

    for col_idx, freqs in enumerate(pwm):
        x = MARGIN_L + col_idx * COL_W

        # Position number (skip zero)
        pos = start_pos + col_idx
        if pos >= 0:
            pos += 1

        # Highlight canonical
        if pos in canonical:
            d.add(Rect(x, MARGIN_B, COL_W, LOGO_H,
                        fillColor=_colors.HexColor("#fef08a"), fillOpacity=0.3,
                        strokeColor=None))

        # Compute IC
        entropy_val = sum(-f * _math.log2(f) if f > 0 else 0 for f in freqs.values())
        ic = max(0, 2 - entropy_val)
        col_h = (ic / 2) * LOGO_H

        # Stack bases sorted by frequency (smallest at bottom)
        sorted_bases = sorted(freqs.items(), key=lambda kv: kv[1])
        cur_y = MARGIN_B
        for base, freq in sorted_bases:
            if freq <= 0:
                continue
            h = freq * col_h
            d.add(Rect(x + 1, cur_y, COL_W - 2, h,
                        fillColor=_colors.HexColor(BASE_COLORS[base]),
                        strokeColor=None, fillOpacity=0.85))
            if h > 7:
                d.add(String(x + COL_W / 2, cur_y + 1.5,
                              base, fontSize=min(h - 1, COL_W - 4),
                              fontName="Courier-Bold", fillColor=_colors.white,
                              textAnchor="middle"))
            cur_y += h

        # Position label
        label = f"+{pos}" if pos > 0 else str(pos)
        is_canon = pos in canonical
        d.add(String(x + COL_W / 2, MARGIN_B - 12, label,
                      fontSize=6 if not is_canon else 7,
                      fontName="Courier-Bold" if is_canon else "Courier",
                      fillColor=_colors.HexColor("#b45309") if is_canon else _colors.HexColor("#94a3b8"),
                      textAnchor="middle"))

    # X-axis title
    site_label = "5'SS donor position" if site == "donor" else "3'SS acceptor position"
    d.add(String(MARGIN_L + seq_len * COL_W / 2, 3, site_label,
                  fontSize=7, fontName="Helvetica-Oblique", fillColor=_colors.HexColor("#475569"),
                  textAnchor="middle"))

    # Baseline
    d.add(Line(MARGIN_L, MARGIN_B, MARGIN_L + seq_len * COL_W, MARGIN_B,
                strokeColor=_colors.HexColor("#475569"), strokeWidth=0.8))

    return d


def _build_pdf(analysis, events: list, features: dict, group1_label: str = "Group 1", group2_label: str = "Group 2") -> bytes:
    global _FIG_NUM
    _FIG_NUM = 0

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=_A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=_MARGIN,
    )
    S = _build_styles()
    story = []

    def p(text: str, style: str = "body") -> Paragraph:
        return Paragraph(text, S[style])

    def sp(h: float = 0.3) -> Spacer:
        return Spacer(1, h * _cm)

    def hr() -> HRFlowable:
        return HRFlowable(width="100%", thickness=0.5, color=_colors.HexColor("#e2e8f0"), spaceAfter=6)

    def caption(text: str) -> Paragraph:
        """Figure caption with auto-numbering."""
        n = _next_fig()
        return Paragraph(
            f"<b>Figure {n}.</b> {text}",
            ParagraphStyle("Caption", parent=S["small"], spaceBefore=4, spaceAfter=10,
                           alignment=TA_CENTER, fontSize=7.5, leading=10,
                           textColor=_colors.HexColor("#475569")),
        )

    # ── Title page ──────────────────────────────────────────────────────────
    story += [
        sp(3),
        p("rMATS-Viz Analysis Report", "h1"),
        hr(),
        sp(0.3),
        p(f"<b>Analysis:</b> {analysis.name}", "body"),
        p(f"<b>Generated:</b> {_date.today().isoformat()}", "body"),
        p(f"<b>Identifier:</b> {analysis.id}", "small"),
    ]

    story.append(p(f"<b>Groups:</b> {group1_label} vs {group2_label}", "body"))

    # Mutated genes
    if analysis.mutated_genes:
        gene_names = ", ".join(g.get("symbol", "?") for g in analysis.mutated_genes if g.get("symbol"))
        if gene_names:
            story.append(p(f"<b>Mutated gene(s):</b> {gene_names}", "body"))

    story += [
        sp(0.5),
        p(
            "This report summarises the alternative splicing events identified "
            "by rMATS and annotated via rMATS-Viz (splice sites, reading frame, "
            "MANE transcript, PPT regions, branch point). "
            "All figures are generated from computed splice features and are "
            "suitable for publication (vector graphics, labeled axes).",
            "body",
        ),
        PageBreak(),
    ]

    # ── 1. Summary ──────────────────────────────────────────────────────────
    story.append(p("1. Analysis Summary", "h2"))

    se_events  = [e for e in events if e.event_type == "SE"]
    type_counts: dict[str, int] = {}
    for ev in events:
        type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1

    story += [
        p(f"Total events: <b>{len(events)}</b>", "body"),
        p(f"SE events: <b>{len(se_events)}</b> · "
          f"RI: {type_counts.get('RI', 0)} · "
          f"A3SS: {type_counts.get('A3SS', 0)} · "
          f"A5SS: {type_counts.get('A5SS', 0)} · "
          f"MXE: {type_counts.get('MXE', 0)}", "body"),
    ]

    # Event-type table
    type_tbl = Table(
        [["Type", "Event Count", "% of Total"]] +
        [
            [etype,
             type_counts.get(etype, 0),
             f"{type_counts.get(etype, 0) / max(len(events), 1) * 100:.1f}%"]
            for etype in ["SE", "RI", "A3SS", "A5SS", "MXE"]
        ] +
        [["<b>Total</b>", f"<b>{len(events)}</b>", "<b>100%</b>"]],
        colWidths=[4 * _cm, 4 * _cm, 4 * _cm],
    )
    type_tbl.setStyle(_tbl_style())
    story += [sp(), type_tbl, sp()]

    # SE-specific stats
    if features:
        n_feat = len(features)
        n_gt   = sum(1 for f in features.values() if f.donor_is_gt is True)
        n_ag   = sum(1 for f in features.values() if f.acceptor_is_ag is True)
        n_if   = sum(1 for f in features.values() if f.frame_class == "in_frame")
        n_fs   = sum(1 for f in features.values() if f.frame_class == "frameshift")
        n_nc   = sum(1 for f in features.values() if f.frame_class == "non_coding")
        n_bp   = sum(1 for f in features.values() if f.bp_motif_found is True)
        ppt_scores = [f.ppt_score for f in features.values() if f.ppt_score is not None]
        exon_sizes = [f.exon_size for f in features.values() if f.exon_size is not None]

        story += [
            p("SE Splice Feature Statistics:", "h3"),
        ]
        stat_tbl = Table([
            ["Metric", "Value"],
            ["SE events with features", n_feat],
            ["Canonical GT (5'SS)", f"{n_gt} / {n_feat} ({n_gt / n_feat * 100:.1f}%)" if n_feat else "—"],
            ["Canonical AG (3'SS)", f"{n_ag} / {n_feat} ({n_ag / n_feat * 100:.1f}%)" if n_feat else "—"],
            ["In-frame",   f"{n_if} ({n_if / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Frameshift", f"{n_fs} ({n_fs / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Non-coding", f"{n_nc} ({n_nc / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Branch point detected", f"{n_bp} / {n_feat} ({n_bp / n_feat * 100:.1f}%)" if n_feat else "—"],
            ["Exon size (mean / median)",
             f"{_statistics.mean(exon_sizes):.0f} / {_statistics.median(exon_sizes):.0f} nt" if exon_sizes else "—"],
            ["Mean PPT score",
             f"{_statistics.mean(ppt_scores) * 100:.1f}% pyrimidine content" if ppt_scores else "—"],
        ], colWidths=[9 * _cm, 7 * _cm])
        stat_tbl.setStyle(_tbl_style())
        story += [stat_tbl, sp()]

    # ── 2. Figures ─────────────────────────────────────────────────────────
    story.append(p("2. Splice Feature Figures", "h2"))

    # Figure: ΔΨ distribution
    dpsi_fig = _fig_dpsi_distribution(events, group1_label, group2_label)
    if dpsi_fig:
        story += [
            KeepTogether([
                dpsi_fig,
                caption(
                    "Distribution of ΔΨ (inclusion level difference) across all events. "
                    f"Red bars: ΔΨ &lt; 0 (more exon skipping in {group1_label}); "
                    f"blue bars: ΔΨ &gt; 0 (more exon inclusion in {group1_label}). "
                    f"n = {len(events)} events."
                ),
            ]),
            sp(),
        ]

    if features:
        exon_sizes_list = [f.exon_size for f in features.values() if f.exon_size is not None]

        # Figure: Exon size histogram
        hist_fig = _fig_exon_size_histogram(exon_sizes_list)
        if hist_fig:
            story += [
                KeepTogether([
                    hist_fig,
                    caption(
                        f"Skipped exon size distribution (25 nt bins). "
                        f"Mean = {_statistics.mean(exon_sizes_list):.0f} nt (red dashed), "
                        f"median = {_statistics.median(exon_sizes_list):.0f} nt (orange dashed). "
                        f"n = {len(exon_sizes_list)} SE events."
                    ),
                ]),
                sp(),
            ]

        # Figure: Frame breakdown
        frame_fig = _fig_frame_breakdown(n_if, n_fs, n_nc, n_feat)
        if frame_fig:
            story += [
                KeepTogether([
                    frame_fig,
                    caption(
                        "Reading-frame classification of skipped exons. "
                        "In-frame: CDS length divisible by 3; "
                        "frameshift: not divisible by 3; "
                        "non-coding: exon entirely within UTR. "
                        f"n = {n_feat} SE events."
                    ),
                ]),
                sp(),
            ]

        # Figure: 5'SS donor sequence logo
        donor_logo = _fig_splice_site_consensus(features, site="donor")
        if donor_logo:
            story += [
                KeepTogether([
                    donor_logo,
                    caption(
                        "5'SS donor splice site sequence logo (9 nt window: 3 nt exon + 6 nt intron). "
                        "Letter height ∝ frequency × information content (bits). "
                        "Canonical GT dinucleotide at positions +1/+2 highlighted in amber. "
                        f"n = {sum(1 for f in features.values() if f.donor_seq and len(f.donor_seq) >= 9)} sequences. "
                        "Method: Schneider &amp; Stephens (1990)."
                    ),
                ]),
                sp(),
            ]

        # Figure: 3'SS acceptor sequence logo
        acceptor_logo = _fig_splice_site_consensus(features, site="acceptor")
        if acceptor_logo:
            story += [
                KeepTogether([
                    acceptor_logo,
                    caption(
                        "3'SS acceptor splice site sequence logo (23 nt window: 20 nt intron + 3 nt exon). "
                        "Letter height ∝ frequency × information content (bits). "
                        "Canonical AG dinucleotide at positions −2/−1 highlighted in amber. "
                        f"n = {sum(1 for f in features.values() if f.acceptor_seq and len(f.acceptor_seq) >= 23)} sequences. "
                        "Method: Schneider &amp; Stephens (1990)."
                    ),
                ]),
                sp(),
            ]

    # ── 3. Top SE events ──────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(p("3. Top SE Events (ranked by FDR, |ΔΨ|)", "h2"))
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
          "<b>rMATS</b> (Shen et al., 2014) from aligned RNA-seq data. The output "
          "files used are junction read counts (<i>.MATS.JC.txt</i>). Events are "
          "filtered according to FDR and |ΔΨ| thresholds set at import.", "body"),
        p("<b>2. Splice Site Annotation</b>", "h3"),
        p("For each SE event, rMATS-Viz extracts flanking genomic sequences from "
          "the GRCh38 (hg38) reference genome indexed with <b>samtools faidx</b>. "
          "Extracted windows are:", "body"),
        p("• <b>5'SS donor:</b> 3 nt exon + 6 nt intron (9 nt window) — see Figure for sequence logo", "body"),
        p("• <b>3'SS acceptor:</b> 20 nt intron + 3 nt exon (23 nt window) — see Figure for sequence logo", "body"),
        p("• <b>PPT:</b> ~47 nt upstream of the acceptor site", "body"),
        p("The canonical GT-AG rule is verified for each event. The PPT score is "
          "defined as the fraction of pyrimidine nucleotides (C, T) in the PPT "
          "window. The branch point is searched by matching the YNYURAY motif in "
          "the PPT region.", "body"),
        p("<b>3. Reading Frame Classification</b>", "h3"),
        p("The skipped exon is classified by its reading-frame impact "
          "(see Figure for proportions):", "body"),
        p("• <b>in_frame:</b> CDS length of the exon divisible by 3 — protein domain loss without frameshift", "body"),
        p("• <b>frameshift:</b> CDS length not divisible by 3 — likely NMD or truncated protein", "body"),
        p("• <b>non_coding:</b> exon entirely within a UTR region — regulatory impact", "body"),
        p("<b>4. MANE Select Annotation</b>", "h3"),
        p("The <b>MANE Select</b> transcript is identified via the Ensembl REST "
          "API (/lookup/id). The skipped exon is mapped onto the transcript. "
          "Ensembl results are cached in a local SQLite database to avoid "
          "repeated API calls.", "body"),
        p("<b>5. Deep Analysis (Significant vs Non-Significant)</b>", "h3"),
        p("Events are classified as significant (FDR ≤ threshold, |ΔΨ| ≥ minimum) "
          "and compared using Welch's t-test (continuous features) and two-proportion "
          "z-test (categorical features). This enables identification of splice-signal "
          "differences between differentially spliced and background events.", "body"),
        sp(),
    ]

    # ── Appendix B — References ──────────────────────────────────────────────
    story += [
        p("Appendix B — Bibliographic References", "h2"),
        hr(),
        p("[1] Shen S et al. <i>rMATS: robust and flexible detection of differential "
          "alternative splicing from replicate RNA-Seq data.</i> PNAS. 2014.", "body"),
        p("[2] Schneider TD, Stephens RM. <i>Sequence logos: a new way to display "
          "consensus sequences.</i> Nucleic Acids Res. 1990;18(20):6097-6100.", "body"),
        p("[3] Burge C, Karlin S. <i>Prediction of complete gene structures in human "
          "genomic DNA.</i> J Mol Biol. 1997;268(1):78-94.", "body"),
        p("[4] Shapiro MB, Senapathy P. <i>RNA splice junctions of different classes "
          "of eukaryotes: sequence statistics and functional implications in gene "
          "expression.</i> Nucleic Acids Res. 1987;15(17):7155-7174.", "body"),
        p("[5] Ensembl REST API: https://rest.ensembl.org", "body"),
        p("[6] MANE Select: Morales J et al. <i>A joint NCBI and EMBL-EBI "
          "transcript set for clinical genomics and research.</i> Nature. 2022.", "body"),
        p("[7] Gene Ontology Consortium. <i>The Gene Ontology resource.</i> "
          "Nucleic Acids Res. 2021.", "body"),
        p("[8] Szklarczyk D et al. <i>STRING v12: protein–protein association "
          "networks with increased coverage.</i> Nucleic Acids Res. 2023.", "body"),
        p("[9] Coolidge CJ, Seely RJ, Bhatt H. <i>Functional analysis of the "
          "polypyrimidine tract in pre-mRNA splicing.</i> Nucleic Acids Res. 1997.", "body"),
        p("[10] Padgett RA et al. <i>Lariat RNAs as intermediates and products in the "
          "splicing of messenger RNA precursors.</i> Science. 1984.", "body"),
        sp(),
    ]

    # ── Appendix C — Statistical Methods ────────────────────────────────────
    story += [
        p("Appendix C — Statistical Methods", "h2"),
        hr(),
        p("<b>Splicing Event Statistic (rMATS)</b>", "h3"),
        p("rMATS computes for each event:", "body"),
        p("• <b>ΔΨ (delta-PSI)</b>: inclusion difference between the two "
          "conditions (Group 2 − Group 1). Ranges from −1 to +1.", "body"),
        p("• <b>p-value</b>: based on a Bayesian permutation test or a t-test "
          "on replicates.", "body"),
        p("• <b>FDR</b>: Benjamini-Hochberg correction applied across all "
          "p-values of the analysis. Canonical threshold: FDR &lt; 0.05.", "body"),
        p("<b>Motif Analysis (rMATS-Viz)</b>", "h3"),
        p("• <b>PWM (Position Weight Matrix)</b>: computed over all 5'SS (9 nt) "
          "and 3'SS (23 nt) sequences from analysed SE events. Each position is "
          "normalised to base frequencies (A, C, G, T).", "body"),
        p("• <b>Information content</b>: IC = 2 − H(p) bits per position, "
          "where H(p) is the Shannon entropy. Sequence logos follow the WebLogo "
          "convention (Schneider &amp; Stephens, 1990).", "body"),
        p("• <b>PPT score</b>: fraction of pyrimidine nucleotides (C, T) in "
          "the ~47 nt window upstream of the acceptor site.", "body"),
        p("<b>Deep Analysis — Statistical Tests</b>", "h3"),
        p("Events are separated into significant and non-significant groups "
          "based on user-defined FDR and |ΔΨ| thresholds. The following tests "
          "compare splice features between groups:", "body"),
        p("• <b>Welch's t-test</b> (unequal variances): compares mean ΔΨ, exon size, "
          "and PPT score between groups.", "body"),
        p("• <b>Two-proportion z-test</b>: compares rates of canonical GT, canonical AG, "
          "in-frame exons, and branch-point detection between groups.", "body"),
        p("P-values are two-tailed. Welch-Satterthwaite degrees of freedom are used "
          "for the t-distribution approximation. The regularised incomplete beta function "
          "is computed via Lentz's continued fraction algorithm.", "body"),
        sp(),
    ]

    doc.build(story)
    return buf.getvalue()


@router.get("/{analysis_id}/pdf")
async def export_analysis_pdf(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Generate a PDF analysis report for *analysis_id*."""

    analysis_q = await db.execute(
        select(Analysis).options(selectinload(Analysis.sample_groups)).where(Analysis.id == analysis_id)
    )
    analysis = analysis_q.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Resolve group labels
    g1 = next((g for g in analysis.sample_groups if g.group_index == 1), None)
    g2 = next((g for g in analysis.sample_groups if g.group_index == 2), None)
    group1_label = g1.group_label if g1 else "Group 1"
    group2_label = g2.group_label if g2 else "Group 2"

    result = await db.execute(
        select(SplicingEvent).where(SplicingEvent.analysis_id == analysis_id)
    )
    events: list[SplicingEvent] = list(result.scalars().all())

    se_event_ids = [e.id for e in events if e.event_type == "SE"]
    features: dict[uuid.UUID, EventSpliceFeature] = {}
    if se_event_ids:
        feat_result = await db.execute(
            select(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(se_event_ids))
        )
        for feat in feat_result.scalars().all():
            features[feat.event_id] = feat

    pdf_bytes = await asyncio.to_thread(_build_pdf, analysis, events, features, group1_label, group2_label)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_{analysis_id}.pdf"'
        },
    )
