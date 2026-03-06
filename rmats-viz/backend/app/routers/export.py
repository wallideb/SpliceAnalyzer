from __future__ import annotations

import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
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
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all splicing events for *analysis_id* as an Excel .xlsx file."""

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

    # ── 4. Build the workbook ─────────────────────────────────────────────────
    wb = openpyxl.Workbook()

    # ── Sheet 1 : Événements ──────────────────────────────────────────────────
    ws_events = wb.active
    ws_events.title = "Événements"

    headers = [
        "Gène", "Gene ID", "Type", "Chromo", "Brin",
        "Exon début", "Exon fin", "Taille exon",
        "p-value", "FDR", "ΔΨ", "|ΔΨ|",
        "PSI groupe 1", "PSI groupe 2",
        "Rang top",
        # SE splice features
        "Site donneur", "Canonique GT",
        "Site accepteur", "Canonique AG",
        "Score PPT", "Run Y max",
        "BP trouvé", "BP distance",
        # Frame / MANE annotations
        "Phase", "Région", "Longueur CDS",
        "Transcrit MANE", "Rang exon",
    ]
    ws_events.append(headers)

    for event in events:
        feat = features.get(event.id) if event.event_type == "SE" else None

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
        ws_events.append(row)

    _style_header_row(ws_events)
    _apply_row_banding(ws_events)
    _auto_size_columns(ws_events)
    ws_events.freeze_panes = "A2"
    ws_events.auto_filter.ref = ws_events.dimensions

    # ── Sheet 2 : Résumé ──────────────────────────────────────────────────────
    ws_summary = wb.create_sheet("Résumé")

    # Count events by type
    type_counts: dict[str, int] = {}
    for event in events:
        type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1

    ws_summary.append(["Type", "Nombre d'événements"])
    for etype in ["SE", "RI", "A3SS", "A5SS", "MXE"]:
        ws_summary.append([etype, type_counts.get(etype, 0)])
    ws_summary.append(["Total", len(events)])

    # SE-specific statistics
    ws_summary.append([])  # blank separator
    ws_summary.append(["Statistiques SE", ""])

    n_se = type_counts.get("SE", 0)
    if n_se > 0 and features:
        n_gt = sum(1 for f in features.values() if f.donor_is_gt is True)
        n_ag = sum(1 for f in features.values() if f.acceptor_is_ag is True)
        n_inframe = sum(
            1 for f in features.values() if f.frame_class == "in-frame"
        )
        n_frameshift = sum(
            1 for f in features.values() if f.frame_class == "frameshift"
        )
        n_feat = len(features)
        ws_summary.append(["SE avec features annotées", n_feat])
        ws_summary.append(["% GT canonique", f"{n_gt / n_feat * 100:.1f}%" if n_feat else "N/A"])
        ws_summary.append(["% AG canonique", f"{n_ag / n_feat * 100:.1f}%" if n_feat else "N/A"])
        ws_summary.append(["% in-frame", f"{n_inframe / n_feat * 100:.1f}%" if n_feat else "N/A"])
        ws_summary.append(["% frameshift", f"{n_frameshift / n_feat * 100:.1f}%" if n_feat else "N/A"])
    else:
        ws_summary.append(["Aucune feature SE annotée", ""])

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

    # ── Page de titre ──────────────────────────────────────────────────────
    story += [
        sp(3),
        p("Rapport d'analyse rMATS-Viz", "h1"),
        hr(),
        sp(0.3),
        p(f"<b>Analyse :</b> {analysis.name}", "body"),
        p(f"<b>Date de génération :</b> {_date.today().isoformat()}", "body"),
        p(f"<b>Identifiant :</b> {analysis.id}", "small"),
        sp(0.5),
        p(
            "Ce rapport synthétise les événements d'épissage alternatif identifiés "
            "par rMATS et annotés via rMATS-Viz (sites d'épissage, cadre de lecture, "
            "transcrit MANE, zones PPT, point de branchement).",
            "body",
        ),
        PageBreak(),
    ]

    # ── Résumé ──────────────────────────────────────────────────────────────
    story.append(p("1. Résumé de l'analyse", "h2"))

    se_events  = [e for e in events if e.event_type == "SE"]
    type_counts: dict[str, int] = {}
    for ev in events:
        type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1

    story += [
        p(f"Nombre total d'événements : <b>{len(events)}</b>", "body"),
        p(f"Événements SE : <b>{len(se_events)}</b> · "
          f"RI : {type_counts.get('RI', 0)} · "
          f"A3SS : {type_counts.get('A3SS', 0)} · "
          f"A5SS : {type_counts.get('A5SS', 0)} · "
          f"MXE : {type_counts.get('MXE', 0)}", "body"),
    ]

    # Event-type table
    type_tbl = Table(
        [["Type", "N événements", "% du total"]] +
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
            p("Statistiques SE (features d'épissage calculées) :", "h3"),
        ]
        stat_tbl = Table([
            ["Métrique", "Valeur"],
            ["Events SE avec features", n_feat],
            ["GT canonique (5'SS)", f"{n_gt / n_feat * 100:.1f}%" if n_feat else "—"],
            ["AG canonique (3'SS)", f"{n_ag / n_feat * 100:.1f}%" if n_feat else "—"],
            ["In-frame",   f"{n_if} ({n_if / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Frameshift", f"{n_fs} ({n_fs / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Non-codant", f"{n_nc} ({n_nc / n_feat * 100:.0f}%)" if n_feat else "—"],
            ["Taille exon (moyenne ± méd.)",
             f"{_statistics.mean(exon_sizes):.0f} ± {_statistics.median(exon_sizes):.0f} nt" if exon_sizes else "—"],
            ["PPT score moyen",
             f"{_statistics.mean(ppt_scores) * 100:.1f}%" if ppt_scores else "—"],
        ], colWidths=[9 * _cm, 7 * _cm])
        stat_tbl.setStyle(_tbl_style())
        story += [stat_tbl, sp()]

    # ── Top événements SE ───────────────────────────────────────────────────
    story.append(p("2. Top événements SE (FDR, |ΔΨ|)", "h2"))
    top_se = sorted(
        [e for e in events if e.event_type == "SE" and e.fdr is not None],
        key=lambda e: (e.fdr or 1, -(abs(e.inc_level_difference or 0))),
    )[:20]

    if top_se:
        top_headers = ["Gène", "Chr", "Brin", "Taille\nexon", "FDR", "ΔΨ", "Phase"]
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
        story.append(p("Aucun événement SE disponible.", "body"))

    story.append(PageBreak())

    # ── Annexe A — Méthodologie ─────────────────────────────────────────────
    story += [
        p("Annexe A — Méthodologie du pipeline", "h2"),
        hr(),
        p("<b>1. Détection des événements d'épissage — rMATS</b>", "h3"),
        p("Les événements d'épissage alternatif (SE, RI, A3SS, A5SS, MXE) sont "
          "détectés par <b>rMATS</b> (Shen et al., 2014) à partir de données "
          "RNA-seq alignées. Les fichiers de sortie utilisés sont les comptages "
          "de jonctions (<i>.MATS.JC.txt</i>). Les événements sont filtrés selon "
          "un seuil de FDR et de |ΔΨ| défini lors de l'import.", "body"),
        p("<b>2. Annotation des sites d'épissage</b>", "h3"),
        p("Pour chaque événement SE, rMATS-Viz extrait les séquences génomiques "
          "flanquantes depuis le génome de référence GRCh38 (hg38) indexé avec "
          "<b>samtools faidx</b>. Les fenêtres extraites sont :", "body"),
        p("• <b>5'SS donneur :</b> 3 nt exon + 6 nt intron (fenêtre de 9 nt)", "body"),
        p("• <b>3'SS accepteur :</b> 20 nt intron + 3 nt exon (fenêtre de 23 nt)", "body"),
        p("• <b>PPT :</b> ~47 nt en amont du site accepteur", "body"),
        p("La règle GT-AG canonique est vérifiée pour chaque événement. Le score "
          "PPT est défini comme la fraction de nucléotides pyrimidiques (C, T) "
          "dans la fenêtre PPT. Le point de branchement est recherché par "
          "correspondance au motif YNYURAY dans la région PPT.", "body"),
        p("<b>3. Annotation MANE Select</b>", "h3"),
        p("Le transcrit <b>MANE Select</b> est identifié via l'API REST d'Ensembl "
          "(/lookup/id). L'exon sauté est cartographié sur le transcrit et classé "
          "selon son impact sur le cadre de lecture :", "body"),
        p("• <b>in_frame :</b> longueur CDS de l'exon divisible par 3", "body"),
        p("• <b>frameshift :</b> longueur CDS non divisible par 3", "body"),
        p("• <b>non_coding :</b> exon entièrement dans une région UTR", "body"),
        p("Les résultats Ensembl sont mis en cache dans une base SQLite locale "
          "pour éviter les appels répétés.", "body"),
        sp(),
    ]

    # ── Annexe B — Références ───────────────────────────────────────────────
    story += [
        p("Annexe B — Références bibliographiques", "h2"),
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

    # ── Annexe C — Tests statistiques ───────────────────────────────────────
    story += [
        p("Annexe C — Tests statistiques appliqués", "h2"),
        hr(),
        p("<b>Statistique de l'événement d'épissage (rMATS)</b>", "h3"),
        p("rMATS calcule pour chaque événement :", "body"),
        p("• <b>ΔΨ (delta-PSI)</b> : différence d'inclusion entre les deux "
          "conditions (Groupe 2 − Groupe 1). Varie entre −1 et +1.", "body"),
        p("• <b>p-value</b> : basée sur un test de permutation bayésien ou un "
          "test t sur les réplicats.", "body"),
        p("• <b>FDR</b> : correction de Benjamini-Hochberg appliquée sur l'ensemble "
          "des p-values de l'analyse. Seuil classique : FDR < 0.05.", "body"),
        p("<b>Analyse de motifs (rMATS-Viz)</b>", "h3"),
        p("• <b>PWM (Position Weight Matrix)</b> : calculée sur l'ensemble des "
          "séquences 5'SS (9 nt) et 3'SS (23 nt) des événements SE analysés. "
          "Chaque position est normalisée en fréquences de bases (A, C, G, T).", "body"),
        p("• <b>Information content</b> : IC = 2 − H(p) bits par position, "
          "où H(p) est l'entropie de Shannon. Les logos de séquences suivent "
          "la convention WebLogo (Schneider & Stephens, 1990).", "body"),
        p("• <b>Score PPT</b> : fraction de nucléotides pyrimidiques (C, T) "
          "dans la fenêtre de ~47 nt en amont du site accepteur.", "body"),
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

    import asyncio as _asyncio
    pdf_bytes = await _asyncio.to_thread(_build_pdf, analysis, events, features)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rmats_{analysis_id}.pdf"'
        },
    )
