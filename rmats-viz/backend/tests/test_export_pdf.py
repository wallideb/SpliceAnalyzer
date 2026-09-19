"""
Smoke tests for the PDF report builder (``routers/export._build_pdf``) with
synthetic ORM objects: every optional block (comparison with q-values, the
4-row permutation table, hnRNP 7-region results with untestable pairs,
Enrichr terms, features without frames / with unknown canonical-site flags)
must render without raising.

Run:  cd rmats-viz/backend && python -m pytest tests/test_export_pdf.py -q
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.analysis import Analysis  # noqa: E402
from app.models.deep_analysis import DeepAnalysis  # noqa: E402
from app.models.event import SplicingEvent  # noqa: E402
from app.models.splice import EventSpliceFeature  # noqa: E402
from app.routers.deep_analyses import _compute_group_stats, _compute_stat_tests  # noqa: E402
from app.routers.export import _build_pdf, _fig_frame_breakdown  # noqa: E402
from app.services.hnrnp_motifs import HNRNP_MOTIFS, REGION_NAMES  # noqa: E402

_PDF_MAGIC = b"%PDF"


def _analysis() -> Analysis:
    return Analysis(id=uuid.uuid4(), name="Smoke test", status="ready",
                    mutated_genes=[{"symbol": "PCBP1"}])


def _deep(analysis: Analysis, pvalue_threshold: float | None = None) -> DeepAnalysis:
    return DeepAnalysis(
        id=uuid.uuid4(), analysis_id=analysis.id, name="DA smoke", status="ready",
        fdr_threshold=0.05, delta_psi_min=0.1, pvalue_threshold=pvalue_threshold,
        modules=[], n_significant=0, n_not_significant=0,
    )


def _event(analysis: Analysis, i: int, event_type: str = "SE", strand: str = "+") -> SplicingEvent:
    base = 10_000 * (i + 1)
    return SplicingEvent(
        id=uuid.uuid4(), analysis_id=analysis.id, event_type=event_type,
        gene_id=f"ENSG{i:011d}", gene_symbol=f"GENE{i}", chr=f"chr{(i % 22) + 1}", strand=strand,
        exon_start=base + 1000, exon_end=base + 1100,
        upstream_es=base + 500, upstream_ee=base + 600,
        downstream_es=base + 1500, downstream_ee=base + 1600,
        p_value=0.001 * (i + 1), fdr=0.01 * (i + 1),
        inc_level_1="0.9,0.8,0.85", inc_level_2="0.2,0.3,0.25",
        inc_level_difference=0.6 - 0.02 * i,
    )


def _feature(ev: SplicingEvent, *, with_seq: bool = True, frame: str | None = "in_frame",
             gt: bool | None = True, ag: bool | None = True) -> EventSpliceFeature:
    return EventSpliceFeature(
        id=uuid.uuid4(), event_id=ev.id,
        exon_size=100, upstream_intron_size=400, downstream_intron_size=400,
        donor_seq="CAGGTAAGT" if with_seq else None,
        acceptor_seq="TTTTTTTTTTTTTTTTTTCAGGT" if with_seq else None,
        ppt_seq=("T" * 20 + "CTCTAAC" + "T" * 20) if with_seq else None,
        upstream_donor_seq="AAGGTGAGT" if with_seq else None,
        downstream_acceptor_seq="CCCCCCCCCCCCCCCCCCCAGAT" if with_seq else None,
        donor_is_gt=gt if with_seq else None, acceptor_is_ag=ag if with_seq else None,
        upstream_donor_is_gt=True if with_seq else None,
        downstream_acceptor_is_ag=True if with_seq else None,
        ppt_score=0.85 if with_seq else None, ppt_longest_run=12 if with_seq else None,
        bp_motif_found=with_seq, bp_distance=25 if with_seq else None, bp_score=7 if with_seq else None,
        bp_position=20 if with_seq else None, bp_motif="CTCTAAC" if with_seq else None,
        frame_class=frame, frame_region="CDS" if frame == "in_frame" else "unknown",
        mane_transcript_id="ENST00000000001" if frame else None,
        sequence_source="fasta" if with_seq else None,
    )


def _hnrnp_data(n_sig: int, n_bg: int) -> dict:
    """One result per motif × region; every other pair untestable (None p)."""
    results = []
    for mi, (motif, protein, _) in enumerate(HNRNP_MOTIFS):
        for ri, region in enumerate(REGION_NAMES):
            testable = (mi + ri) % 2 == 0
            results.append({
                "motif_name": motif, "protein": protein, "region": region,
                "sig_hit_count": n_sig // 2, "sig_total": n_sig,
                "bg_hit_count": n_bg // 3, "bg_total": n_bg,
                "sig_density": 0.12, "bg_density": 0.08,
                "z_stat": 2.1 if testable else None,
                "p_value": 0.03 if testable else None,
                "p_adjusted": 0.04 if testable else None,
                "significant": testable and ri == 0,
                "density_u_stat": 40.0 if testable else None,
                "density_p_value": 0.02 if testable else None,
                "density_p_adjusted": 0.045 if testable else None,
                "density_significant": testable and ri == 3,
                "regulatory_effect": "ESS" if ri == 3 else None,
            })
    return {"n_sig_events": n_sig, "n_bg_events": n_bg,
            "regions": list(REGION_NAMES), "results": results}


def _enrichr_data() -> dict:
    return {
        "n_genes_submitted": 12,
        "terms": [
            {"library": "KEGG_2021_Human", "rank": 1, "term": "Spliceosome",
             "p_value": 1e-4, "adjusted_p_value": 0.002, "z_score": -2.0,
             "combined_score": 18.4, "overlap": "3/150", "genes": ["GENE1", "GENE2", "GENE3"]},
            {"library": "GO_Biological_Process_2023", "rank": 1,
             "term": "mRNA Splicing, Via Spliceosome (GO:0000398)",
             "p_value": 0.01, "adjusted_p_value": 0.2, "z_score": -1.5,
             "combined_score": 6.9, "overlap": "2", "genes": ["GENE1", "GENE4"]},
        ],
    }


# ---------------------------------------------------------------------------

def test_pdf_plain_analysis_without_features():
    an = _analysis()
    events = [_event(an, i, et) for i, et in enumerate(["SE", "SE", "RI", "A3SS", "MXE"])]
    pdf = _build_pdf(an, events, {}, "Subjects", "Controls")
    assert pdf.startswith(_PDF_MAGIC)


def test_pdf_features_without_frames_and_unknown_flags():
    an = _analysis()
    events = [_event(an, i, strand="-" if i % 2 else "+") for i in range(6)]
    feats = {}
    for i, ev in enumerate(events):
        feats[ev.id] = _feature(
            ev, with_seq=(i != 5), frame=None if i < 3 else "unknown",
            gt=None if i == 0 else True, ag=None if i == 1 else False,
        )
    pdf = _build_pdf(an, events, feats, "Subjects", "Controls")
    assert pdf.startswith(_PDF_MAGIC)


def test_pdf_deep_analysis_all_sections():
    an = _analysis()
    deep = _deep(an, pvalue_threshold=0.01)
    events = [_event(an, i) for i in range(16)] + [_event(an, 20, "RI")]
    feats = {ev.id: _feature(ev, frame=["in_frame", "frameshift", "non_coding", "unknown"][i % 4],
                             gt=None if i == 3 else True)
             for i, ev in enumerate(events) if ev.event_type == "SE"}
    sig_map = {ev.id: (i % 2 == 0) for i, ev in enumerate(events)}
    se = [e for e in events if e.event_type == "SE"]
    sig_ev = [e for e in se if sig_map[e.id]]
    ns_ev = [e for e in se if not sig_map[e.id]]
    sig_f = [feats[e.id] for e in sig_ev]
    ns_f = [feats[e.id] for e in ns_ev]
    tests = _compute_stat_tests(sig_ev, sig_f, ns_ev, ns_f)
    comparison = {
        "significant": _compute_group_stats(sig_ev, sig_f).model_dump(),
        "not_significant": _compute_group_stats(ns_ev, ns_f).model_dump(),
        "statistical_tests": [
            {"feature": t.feature, "test_name": t.test_name, "statistic": t.statistic,
             "p_value": t.p_value, "q_value": t.q_value, "significant": t.significant,
             "significant_fdr": t.significant_fdr}
            for t in tests
        ],
    }
    assert any(t["feature"].endswith("_mwu") for t in comparison["statistical_tests"])
    perm_table = [
        {"iterations": k, "n_tested": len(sig_ev), "pct_p05": 37.5, "pct_p01": None,
         "exact_fraction": 1.0, "min_p_attainable": 0.05,
         "n_replicates_g1": 3, "n_replicates_g2": 3}
        for k in (50, 100, 250, 500)
    ]
    pdf = _build_pdf(
        an, events, feats, "Subjects", "Controls",
        deep_analysis=deep, comparison=comparison, sig_map=sig_map,
        permutation_table=perm_table,
        hnrnp_data=_hnrnp_data(len(sig_ev), len(ns_ev)),
        enrichr_data=_enrichr_data(),
    )
    assert pdf.startswith(_PDF_MAGIC)


def test_pdf_deep_analysis_empty_optional_blocks():
    an = _analysis()
    deep = _deep(an)
    events = [_event(an, i) for i in range(4)]
    feats = {ev.id: _feature(ev, with_seq=False, frame=None) for ev in events}
    sig_map = {ev.id: True for ev in events}
    pdf = _build_pdf(
        an, events, feats, "Subjects", "Controls",
        deep_analysis=deep, comparison=None, sig_map=sig_map,
        permutation_table=[], hnrnp_data={"n_sig_events": 4, "n_bg_events": 0,
                                          "regions": list(REGION_NAMES), "results": []},
        enrichr_data={"n_genes_submitted": 0, "terms": []},
    )
    assert pdf.startswith(_PDF_MAGIC)


def test_frame_breakdown_denominator_excludes_unknown():
    assert _fig_frame_breakdown(0, 0, 0, 10) is None
    d = _fig_frame_breakdown(3, 1, 0, 6)
    assert d is not None
    labels = [c.text for c in d.contents if hasattr(c, "text")]
    assert any("75%" in t for t in labels)            # 3 / 4 known, not 3 / 10
    assert any("6 unknown" in t and "n = 4 known" in t for t in labels)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
