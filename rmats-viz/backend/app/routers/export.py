from __future__ import annotations

import asyncio
import uuid
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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

    # ── 1. Verify analysis exists ─────────────────────────────────────────────
    analysis = await db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

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
        "PSI Group 1", "PSI Group 2",
        "Top Rank",
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
            event.top_rank,
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
    PageBreak, HRFlowable,
)

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


def _build_pdf(analysis, events: list, features: dict) -> bytes:
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

    # ── Title page ──────────────────────────────────────────────────────────
    story += [
        sp(3),
        p("rMATS-Viz Analysis Report", "h1"),
        hr(),
        sp(0.3),
        p(f"<b>Analysis:</b> {analysis.name}", "body"),
        p(f"<b>Generated:</b> {_date.today().isoformat()}", "body"),
        p(f"<b>Identifier:</b> {analysis.id}", "small"),
        sp(0.5),
        p(
            "This report summarises the alternative splicing events identified "
            "by rMATS and annotated via rMATS-Viz (splice sites, reading frame, "
            "MANE transcript, PPT regions, branch point).",
            "body",
        ),
        PageBreak(),
    ]

    # ── Summary ─────────────────────────────────────────────────────────────
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
        ppt_scores = [f.ppt_score for f in features.values() if f.ppt_score is not None]
        exon_sizes = [f.exon_size for f in features.values() if f.exon_size is not None]

        story += [
            p("SE Splice Feature Statistics:", "h3"),
        ]
        stat_tbl = Table([
            ["Metric", "Value"],
            ["SE events with features", n_feat],
            ["Canonical GT (5'SS)", f"{n_gt / n_feat * 100:.1f}%" if n_feat else "—"],
            ["Canonical AG (3'SS)", f"{n_ag / n_feat * 100:.1f}%" if n_feat else "—"],
            ["In-frame",   f"{n_if} ({n_if / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Frameshift", f"{n_fs} ({n_fs / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Non-coding", f"{n_nc} ({n_nc / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Exon size (mean ± median)",
             f"{_statistics.mean(exon_sizes):.0f} ± {_statistics.median(exon_sizes):.0f} nt" if exon_sizes else "—"],
            ["Mean PPT score",
             f"{_statistics.mean(ppt_scores) * 100:.1f}%" if ppt_scores else "—"],
        ], colWidths=[9 * _cm, 7 * _cm])
        stat_tbl.setStyle(_tbl_style())
        story += [stat_tbl, sp()]

    # ── Top SE events ────────────────────────────────────────────────────────
    story.append(p("2. Top SE Events (FDR, |ΔΨ|)", "h2"))
    top_se = sorted(
        [e for e in events if e.event_type == "SE" and e.fdr is not None],
        key=lambda e: (e.fdr or 1, -(abs(e.inc_level_difference or 0))),
    )[:20]

    if top_se:
        top_headers = ["Gene", "Chr", "Strand", "Exon\nSize", "FDR", "ΔΨ", "Frame"]
        top_rows = [top_headers]
        for ev in top_se:
            feat = features.get(ev.id)
            top_rows.append([
                ev.gene_symbol or "—",
                ev.chr or "—",
                ev.strand or "—",
                str(feat.exon_size) + " nt" if feat and feat.exon_size else "—",
                f"{ev.fdr:.2e}" if ev.fdr is not None else "—",
                f"{ev.inc_level_difference:+.3f}" if ev.inc_level_difference is not None else "—",
                feat.frame_class or "—" if feat else "—",
            ])
        top_tbl = Table(top_rows, colWidths=[3*_cm, 2*_cm, 1.2*_cm, 2*_cm, 2.3*_cm, 2*_cm, 2.5*_cm])
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
        p("• <b>5'SS donor:</b> 3 nt exon + 6 nt intron (9 nt window)", "body"),
        p("• <b>3'SS acceptor:</b> 20 nt intron + 3 nt exon (23 nt window)", "body"),
        p("• <b>PPT:</b> ~47 nt upstream of the acceptor site", "body"),
        p("The canonical GT-AG rule is verified for each event. The PPT score is "
          "defined as the fraction of pyrimidine nucleotides (C, T) in the PPT "
          "window. The branch point is searched by matching the YNYURAY motif in "
          "the PPT region.", "body"),
        p("<b>3. MANE Select Annotation</b>", "h3"),
        p("The <b>MANE Select</b> transcript is identified via the Ensembl REST "
          "API (/lookup/id). The skipped exon is mapped onto the transcript and "
          "classified by its reading-frame impact:", "body"),
        p("• <b>in_frame:</b> CDS length of the exon divisible by 3", "body"),
        p("• <b>frameshift:</b> CDS length not divisible by 3", "body"),
        p("• <b>non_coding:</b> exon entirely within a UTR region", "body"),
        p("Ensembl results are cached in a local SQLite database to avoid "
          "repeated API calls.", "body"),
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
          "p-values of the analysis. Canonical threshold: FDR < 0.05.", "body"),
        p("<b>Motif Analysis (rMATS-Viz)</b>", "h3"),
        p("• <b>PWM (Position Weight Matrix)</b>: computed over all 5'SS (9 nt) "
          "and 3'SS (23 nt) sequences from analysed SE events. Each position is "
          "normalised to base frequencies (A, C, G, T).", "body"),
        p("• <b>Information content</b>: IC = 2 − H(p) bits per position, "
          "where H(p) is the Shannon entropy. Sequence logos follow the WebLogo "
          "convention (Schneider &amp; Stephens, 1990).", "body"),
        p("• <b>PPT score</b>: fraction of pyrimidine nucleotides (C, T) in "
          "the ~47 nt window upstream of the acceptor site.", "body"),
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

    analysis = await db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

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

    pdf_bytes = await asyncio.to_thread(_build_pdf, analysis, events, features)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_{analysis_id}.pdf"'
        },
    )
