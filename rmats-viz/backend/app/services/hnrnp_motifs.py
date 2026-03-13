"""
hnRNP motif enrichment analysis
=================================
Inspired by rMAPS2 (Hwang et al., NAR 2020), this module scans genomic
regions around skipped-exon (SE) events for known hnRNP RNA-binding
protein motifs and compares their frequency between significant (regulated)
and non-significant (background) events.

Methodology
-----------
For each SE event, five regions are defined:

  upstream exon ─── upstream intron ─── [skipped exon] ─── downstream intron ─── downstream exon

Region extraction (per rMAPS2 convention):
  - Upstream exon:      last 250 nt of the upstream exon
  - Upstream intron:    250 nt from the 5'SS, excluding the first 6 nt (splice signal)
  - Skipped exon:       full exon body
  - Downstream intron:  250 nt from the 3'SS, excluding the last 20 nt (splice signal)
  - Downstream exon:    first 250 nt of the downstream exon

Motifs scanned (consensus sequences from literature & CISBP-RNA):
  - hnRNP A1/A2: UAGG, UAGGG, AGG
  - hnRNP F/H:   GGGG, GGG
  - hnRNP K:     CCCC, TCCC
  - hnRNP C:     UUUUU (poly-U 5-mer), UUUU
  - hnRNP L:     CACA, ACAC (CA repeats)
  - hnRNP M:     UGUG, GUGU (GU-rich)
  - PTB (hnRNP I): UCUU, UCUCU, CUCU

For each motif in each region, we compute:
  - motif density = (# occurrences × motif_length) / region_length
  - A proportion z-test (significant vs background) with Bonferroni correction

References
----------
- Hwang JY et al. rMAPS2. Nucleic Acids Res 2020; 48:W300-W306
- Ray D et al. A compendium of RNA-binding motifs. Nature 2013
- Geuens T et al. The hnRNP family. Hum Genet 2016
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
# Motif definitions
# ──────────────────────────────────────────────────────────────────────────────

# Each motif is stored as (name, protein_family, DNA_pattern)
# RNA U → DNA T for scanning genomic DNA sequences.
HNRNP_MOTIFS: list[tuple[str, str, str]] = [
    # hnRNP A1 / A2B1
    ("TAGG",      "hnRNP A1/A2", "TAGG"),
    ("TAGGG",     "hnRNP A1/A2", "TAGGG"),
    ("TAGGGA",    "hnRNP A1/A2", "TAGGGA"),
    ("AGG",       "hnRNP A1/A2", "AGG"),
    # hnRNP F / H (G-runs)
    ("GGGG",      "hnRNP F/H",   "GGGG"),
    ("GGG",       "hnRNP F/H",   "GGG"),
    # hnRNP K (poly-C)
    ("CCCC",      "hnRNP K",     "CCCC"),
    ("TCCC",      "hnRNP K",     "TCCC"),
    # hnRNP C (poly-U → poly-T in DNA)
    ("TTTTT",     "hnRNP C",     "TTTTT"),
    ("TTTT",      "hnRNP C",     "TTTT"),
    # hnRNP L (CA repeats)
    ("CACA",      "hnRNP L",     "CACA"),
    ("ACAC",      "hnRNP L",     "ACAC"),
    # hnRNP M (GU-rich → GT in DNA)
    ("TGTG",      "hnRNP M",     "TGTG"),
    ("GTGT",      "hnRNP M",     "GTGT"),
    # PTB / hnRNP I
    ("TCTT",      "PTB (hnRNP I)", "TCTT"),
    ("TCTCT",     "PTB (hnRNP I)", "TCTCT"),
    ("CTCT",      "PTB (hnRNP I)", "CTCT"),
]

REGION_NAMES = [
    "upstream_exon",
    "upstream_intron",
    "skipped_exon",
    "downstream_intron",
    "downstream_exon",
]

# Intronic exclusion zones (per rMAPS2): 6 nt at 5'SS, 20 nt at 3'SS
_FIVE_SS_EXCL = 6
_THREE_SS_EXCL = 20
# Max region length to extract for flanking exons / introns
_FLANK_LEN = 250


# ──────────────────────────────────────────────────────────────────────────────
# Region extraction
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SERegions:
    """Five genomic regions around a skipped exon for motif scanning."""
    upstream_exon: str = ""
    upstream_intron: str = ""
    skipped_exon: str = ""
    downstream_intron: str = ""
    downstream_exon: str = ""


def define_se_regions(
    chrom: str,
    strand: str,
    exon_start: int,
    exon_end: int,
    upstream_es: int | None,
    upstream_ee: int | None,
    downstream_es: int | None,
    downstream_ee: int | None,
) -> list[tuple[str, int, int]]:
    """Return list of (chrom, start, end) BED regions for the five zones.

    Coordinates are always on the + strand (genomic). Reverse-complement
    is applied after extraction if strand == '-'.
    """
    regions: list[tuple[str, int, int]] = []

    # 1. Upstream exon: last _FLANK_LEN nt
    if upstream_es is not None and upstream_ee is not None:
        up_len = upstream_ee - upstream_es
        take = min(up_len, _FLANK_LEN)
        regions.append((chrom, upstream_ee - take, upstream_ee))
    else:
        regions.append((chrom, 0, 0))

    # 2. Upstream intron: first _FLANK_LEN nt after 5'SS exclusion
    if upstream_ee is not None:
        if strand == "+":
            istart = upstream_ee + _FIVE_SS_EXCL
            iend = min(istart + _FLANK_LEN, exon_start - _THREE_SS_EXCL)
        else:
            iend = upstream_ee - _FIVE_SS_EXCL
            istart = max(iend - _FLANK_LEN, exon_end + _THREE_SS_EXCL)
        if iend > istart:
            regions.append((chrom, istart, iend))
        else:
            regions.append((chrom, 0, 0))
    else:
        regions.append((chrom, 0, 0))

    # 3. Skipped exon body
    regions.append((chrom, exon_start, exon_end))

    # 4. Downstream intron: first _FLANK_LEN nt after exon, excluding splice signals
    if downstream_es is not None:
        if strand == "+":
            istart = exon_end + _FIVE_SS_EXCL
            iend = min(istart + _FLANK_LEN, downstream_es - _THREE_SS_EXCL)
        else:
            iend = exon_start - _FIVE_SS_EXCL
            istart = max(iend - _FLANK_LEN, downstream_ee + _THREE_SS_EXCL if downstream_ee is not None else iend)
        if iend > istart:
            regions.append((chrom, istart, iend))
        else:
            regions.append((chrom, 0, 0))
    else:
        regions.append((chrom, 0, 0))

    # 5. Downstream exon: first _FLANK_LEN nt
    if downstream_es is not None and downstream_ee is not None:
        dn_len = downstream_ee - downstream_es
        take = min(dn_len, _FLANK_LEN)
        regions.append((chrom, downstream_es, downstream_es + take))
    else:
        regions.append((chrom, 0, 0))

    return regions


# ──────────────────────────────────────────────────────────────────────────────
# Motif scanning
# ──────────────────────────────────────────────────────────────────────────────

def count_motif_occurrences(seq: str, motif: str) -> int:
    """Count overlapping occurrences of *motif* in *seq* (case-insensitive)."""
    if not seq or not motif:
        return 0
    seq_u = seq.upper()
    motif_u = motif.upper()
    count = 0
    start = 0
    while True:
        pos = seq_u.find(motif_u, start)
        if pos == -1:
            break
        count += 1
        start = pos + 1
    return count


def motif_density(seq: str, motif: str) -> float:
    """Fraction of nucleotides covered by (possibly overlapping) motif hits."""
    if not seq:
        return 0.0
    n = count_motif_occurrences(seq, motif)
    return min(1.0, (n * len(motif)) / len(seq))


@dataclass
class MotifRegionResult:
    """Motif scan result for one motif in one region across a group of events."""
    motif_name: str
    protein: str
    region: str
    count_events_with_hit: int = 0
    total_events: int = 0
    mean_density: float = 0.0


@dataclass
class MotifEnrichmentResult:
    """Comparison of one motif in one region: significant vs background."""
    motif_name: str
    protein: str
    region: str
    sig_hit_count: int = 0
    sig_total: int = 0
    bg_hit_count: int = 0
    bg_total: int = 0
    sig_density: float = 0.0
    bg_density: float = 0.0
    z_stat: float | None = None
    p_value: float | None = None
    p_adjusted: float | None = None
    significant: bool = False


def scan_group(
    sequences_by_region: list[SERegions],
) -> list[MotifRegionResult]:
    """Scan a group of events and return per-motif per-region stats."""
    results: list[MotifRegionResult] = []
    for motif_name, protein, pattern in HNRNP_MOTIFS:
        for region_name in REGION_NAMES:
            n_with_hit = 0
            densities: list[float] = []
            n_total = 0
            for sr in sequences_by_region:
                seq = getattr(sr, region_name, "")
                if not seq:
                    continue
                n_total += 1
                d = motif_density(seq, pattern)
                densities.append(d)
                if d > 0:
                    n_with_hit += 1
            results.append(MotifRegionResult(
                motif_name=motif_name,
                protein=protein,
                region=region_name,
                count_events_with_hit=n_with_hit,
                total_events=n_total,
                mean_density=sum(densities) / len(densities) if densities else 0.0,
            ))
    return results


def compare_groups(
    sig_results: list[MotifRegionResult],
    bg_results: list[MotifRegionResult],
) -> list[MotifEnrichmentResult]:
    """Compare motif enrichment between significant and background groups.

    Uses a two-proportion z-test at each (motif, region) and applies
    Bonferroni correction across all tests.
    """
    bg_lookup: dict[tuple[str, str], MotifRegionResult] = {
        (r.motif_name, r.region): r for r in bg_results
    }

    raw: list[MotifEnrichmentResult] = []
    for sr in sig_results:
        br = bg_lookup.get((sr.motif_name, sr.region))
        if br is None:
            continue
        z, p = _proportion_z_test(
            sr.count_events_with_hit, sr.total_events,
            br.count_events_with_hit, br.total_events,
        )
        raw.append(MotifEnrichmentResult(
            motif_name=sr.motif_name,
            protein=sr.protein,
            region=sr.region,
            sig_hit_count=sr.count_events_with_hit,
            sig_total=sr.total_events,
            bg_hit_count=br.count_events_with_hit,
            bg_total=br.total_events,
            sig_density=round(sr.mean_density, 6),
            bg_density=round(br.mean_density, 6),
            z_stat=round(z, 4) if z is not None else None,
            p_value=round(p, 6) if p is not None else None,
        ))

    # Bonferroni correction
    n_tests = len([r for r in raw if r.p_value is not None])
    for r in raw:
        if r.p_value is not None and n_tests > 0:
            r.p_adjusted = round(min(r.p_value * n_tests, 1.0), 6)
            r.significant = r.p_adjusted < 0.05
        else:
            r.p_adjusted = None
            r.significant = False

    return raw


# ──────────────────────────────────────────────────────────────────────────────
# Stats helpers
# ──────────────────────────────────────────────────────────────────────────────

def _proportion_z_test(
    k1: int, n1: int, k2: int, n2: int,
) -> tuple[float | None, float | None]:
    """Two-proportion z-test. Returns (z, p) or (None, None)."""
    if n1 < 1 or n2 < 1:
        return None, None
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return None, None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    p = 2 * (1 - _normal_cdf(abs(z)))
    return z, p


def _normal_cdf(x: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun)."""
    return 0.5 * math.erfc(-x / math.sqrt(2))
