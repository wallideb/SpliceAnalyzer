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
  - hnRNP E1 (PCBP1): CCWWHCC  [CC[AT][AT][ACT]CC — rMAPS2 Suppl. Table S2, Homo sapiens]
  - hnRNP E2 (PCBP2): CCYYCCH  [CC[CT][CT]CC[ACT] — rMAPS2 Suppl. Table S2, Homo sapiens]
  - hnRNP F/H:   GGGG, GGG
  - hnRNP K:     CCCC, TCCC
  - hnRNP C:     UUUUU (poly-U 5-mer), UUUU
  - hnRNP L:     CACA, ACAC (CA repeats)
  - hnRNP M:     UGUG, GUGU (GU-rich)
  - PTB (hnRNP I): UCUU, UCUCU, CUCU

For each motif in each region, we compute:
  - motif density = (# occurrences × motif_length) / region_length  [descriptive]
  - A standard pooled two-proportion z-test on binary hit presence
    (event hit / no-hit) between significant and background groups.
    This is a large-sample normal approximation, not an exact test.
  - Raw p-values are adjusted across all testable (motif × region) pairs
    using the Benjamini-Hochberg FDR procedure.  A pair is called
    significant at q < 0.05 (expected FDR ≤ 5 %).

Note
----
rMAPS2 uses a sliding window (default 50 bp) with Wilcoxon rank-sum test on
per-window motif density, and separates events into upregulated, downregulated,
and background groups.  Our simplified implementation uses a two-proportion
z-test on binary motif presence per region, comparing significant vs
non-significant events.  BH is preferred over Bonferroni for this exploratory
screen because it controls the proportion of false positives among discoveries
rather than the probability of any false positive in the family.

References
----------
- Hwang JY, Jung S, Kook TL, Rouchka EC, Bok J, Park JW. rMAPS2.
  Nucleic Acids Res 2020; 48:W300-W306 (doi:10.1093/nar/gkaa237)
- Ray D et al. A compendium of RNA-binding motifs. Nature 2013; 499:172-177
- Martinez-Contreras R et al. Intronic binding sites for hnRNP A/B and
  hnRNP F/H proteins stimulate pre-mRNA splicing. PLoS Biol 2006; 4:e21
- Geuens T et al. The hnRNP family. Hum Genet 2016
- Chkheidze AN et al. Assembly of the alpha-complex on the 3' UTR of the
  human alpha-globin mRNA. Mol Cell Biol 1999; 19:4572-4581
- Makeyev AV & Liebhaber SA. The poly(C)-binding proteins. RNA 2002; 8:265-278
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
    # hnRNP E — PCBP1 (E1) & PCBP2 (E2) degenerate 7-mers from rMAPS2 Supplementary Table S2 (Homo sapiens)
    # PCBP1 CCWWHCC: CC[AT][AT][ACT]CC  (IUPAC W=A/T, H=A/C/T)  ENSG00000169564
    # PCBP2 CCYYCCH: CC[CT][CT]CC[ACT]  (IUPAC Y=C/T, H=A/C/T)  ENSG00000197111
    # Chkheidze et al. Mol Cell Biol 1999; Makeyev & Liebhaber RNA 2002; CISBP-RNA Ray 2013
    ("CCWWHCC",   "hnRNP E1 (PCBP1)", "CC[AT][AT][ACT]CC"),
    ("CCYYCCH",   "hnRNP E2 (PCBP2)", "CC[CT][CT]CC[ACT]"),
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

def _motif_match_len(pattern: str) -> int:
    """Return the number of nucleotides consumed by one match of *pattern*.

    Handles IUPAC bracket groups (e.g. ``[AT]`` counts as 1 position).
    """
    length, in_bracket = 0, False
    for ch in pattern:
        if ch == '[':
            in_bracket = True
        elif ch == ']':
            in_bracket = False
            length += 1
        elif not in_bracket:
            length += 1
    return length


# Pre-compiled regex patterns and their match lengths — computed once at import.
# Using regex for all patterns allows degenerate IUPAC bracket notation while
# remaining backwards-compatible with plain literal motifs (valid regex too).
_COMPILED_MOTIFS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(pattern), _motif_match_len(pattern))
    for _, _, pattern in HNRNP_MOTIFS
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

    Strand conventions (all positions are 0-based genomic):
    rMATS ALWAYS uses genomic ordering: upstream_*=lower coords, downstream_*=higher coords.
    True genomic layout for both strands:
      [upstream_es … upstream_ee) ── intron ── [exon_start … exon_end) ── intron ── [downstream_es … downstream_ee)

    + strand: upstream exon is 5′ in transcript (lower coords); downstream is 3′ (higher coords).
    - strand: rMATS "upstream" exon (lower coords) is 3′ in transcript;
              rMATS "downstream" exon (higher coords) is 5′ in transcript.
              Upstream intron (5′ of skipped) spans [exon_end, downstream_es).
              Downstream intron (3′ of skipped) spans [upstream_ee, exon_start).
    """
    regions: list[tuple[str, int, int]] = []

    # 1. Upstream exon (5′ flanking): _FLANK_LEN nt closest to the upstream intron.
    #    + strand: 5′ flanking = rMATS upstream exon; intron-proximal end at upstream_ee
    #              → [upstream_ee - take, upstream_ee)
    #    - strand: 5′ flanking = rMATS downstream exon (higher coords); intron-proximal end
    #              at downstream_es (LOW boundary of that exon) → [downstream_es, downstream_es + take)
    if strand == "+":
        if upstream_es is not None and upstream_ee is not None:
            take = min(upstream_ee - upstream_es, _FLANK_LEN)
            regions.append((chrom, upstream_ee - take, upstream_ee))
        else:
            regions.append((chrom, 0, 0))
    else:
        if downstream_es is not None and downstream_ee is not None:
            take = min(downstream_ee - downstream_es, _FLANK_LEN)
            regions.append((chrom, downstream_es, downstream_es + take))
        else:
            regions.append((chrom, 0, 0))

    # 2. Upstream intron (5′ of skipped exon): first _FLANK_LEN nt after 5'SS exclusion.
    #    + strand: 5'SS at upstream_ee; intron spans [upstream_ee, exon_start)
    #              → exclude [upstream_ee, upstream_ee+6); body starts at upstream_ee+6
    #    - strand: 5'SS at downstream_es (LOW boundary of rMATS downstream exon);
    #              intron spans [exon_end, downstream_es) in genomic space;
    #              in transcript direction intron is read from downstream_es down to exon_end.
    #              → exclude [downstream_es-6, downstream_es); body ends at downstream_es-6
    if strand == "+":
        if upstream_ee is not None:
            istart = upstream_ee + _FIVE_SS_EXCL
            iend = min(istart + _FLANK_LEN, exon_start - _THREE_SS_EXCL)
            regions.append((chrom, istart, iend) if iend > istart else (chrom, 0, 0))
        else:
            regions.append((chrom, 0, 0))
    else:
        if downstream_es is not None:
            iend = downstream_es - _FIVE_SS_EXCL
            istart = max(iend - _FLANK_LEN, exon_end + _THREE_SS_EXCL)
            regions.append((chrom, istart, iend) if iend > istart else (chrom, 0, 0))
        else:
            regions.append((chrom, 0, 0))

    # 3. Skipped exon body
    regions.append((chrom, exon_start, exon_end))

    # 4. Downstream intron (3′ of skipped exon): first _FLANK_LEN nt after 5'SS exclusion.
    #    + strand: 5'SS at exon_end; intron spans [exon_end, downstream_es)
    #              → exclude [exon_end, exon_end+6); bound by downstream_es - 20
    #    - strand: 5'SS at exon_start (LOW boundary of skipped exon = 3' end in transcript);
    #              intron spans [upstream_ee, exon_start) in genomic space;
    #              in transcript direction read from exon_start down to upstream_ee.
    #              → exclude [exon_start-6, exon_start); bound by upstream_ee + 20
    if strand == "+":
        if downstream_es is not None:
            istart = exon_end + _FIVE_SS_EXCL
            iend = min(istart + _FLANK_LEN, downstream_es - _THREE_SS_EXCL)
            regions.append((chrom, istart, iend) if iend > istart else (chrom, 0, 0))
        else:
            regions.append((chrom, 0, 0))
    else:
        if upstream_ee is not None:
            iend = exon_start - _FIVE_SS_EXCL
            istart = max(iend - _FLANK_LEN, upstream_ee + _THREE_SS_EXCL)
            regions.append((chrom, istart, iend) if iend > istart else (chrom, 0, 0))
        else:
            regions.append((chrom, 0, 0))

    # 5. Downstream exon (3′ flanking): _FLANK_LEN nt closest to the downstream intron.
    #    + strand: 3′ flanking = rMATS downstream exon; intron-proximal end at downstream_es
    #              → [downstream_es, downstream_es + take)
    #    - strand: 3′ flanking = rMATS upstream exon (lower coords); intron-proximal end
    #              at upstream_ee (HIGH boundary of that exon) → [upstream_ee - take, upstream_ee)
    if strand == "+":
        if downstream_es is not None and downstream_ee is not None:
            take = min(downstream_ee - downstream_es, _FLANK_LEN)
            regions.append((chrom, downstream_es, downstream_es + take))
        else:
            regions.append((chrom, 0, 0))
    else:
        if upstream_es is not None and upstream_ee is not None:
            take = min(upstream_ee - upstream_es, _FLANK_LEN)
            regions.append((chrom, upstream_ee - take, upstream_ee))
        else:
            regions.append((chrom, 0, 0))

    return regions


# ──────────────────────────────────────────────────────────────────────────────
# Motif scanning
# ──────────────────────────────────────────────────────────────────────────────

def count_motif_occurrences(seq: str, motif: str) -> int:
    """Count overlapping occurrences of *motif* in *seq* (case-insensitive).

    *motif* may contain IUPAC bracket notation (e.g. ``CC[AT][AT][ACT]CC``).
    """
    if not seq or not motif:
        return 0
    compiled = re.compile(motif.upper())
    seq_u = seq.upper()
    count = 0
    pos = 0
    while True:
        m = compiled.search(seq_u, pos)
        if m is None:
            break
        count += 1
        pos = m.start() + 1
    return count


def motif_density(seq: str, motif: str) -> float:
    """Fraction of nucleotides covered by (possibly overlapping) motif hits."""
    if not seq:
        return 0.0
    n = count_motif_occurrences(seq, motif)
    return min(1.0, (n * _motif_match_len(motif.upper())) / len(seq))


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
    """Scan a group of events and return per-motif per-region stats.

    Performance notes (optimised for 120 k-event datasets):
    - Iterates events in the *outer* loop so each SERegions object is
      accessed once → better cache locality.
    - Skips redundant ``str.upper()`` calls: sequences produced by
      ``extract_regions_batch`` are already uppercase; motif patterns in
      ``HNRNP_MOTIFS`` are defined uppercase.
    - Uses ``compiled.search`` as an early-exit hit check before the
      overlapping-count loop, skipping the count for ~50-80 % of pairs.
      Pre-compiled regex handles both plain literals and degenerate IUPAC
      bracket patterns (e.g. CC[AT][AT][ACT]CC) without branching.
    - Accumulates a running density sum instead of building per-region
      lists, eliminating repeated list allocations.
    """
    n_motifs = len(HNRNP_MOTIFS)
    n_regions = len(REGION_NAMES)

    # Flat pre-allocated accumulators: index = mi * n_regions + ri
    n_totals = [0]   * (n_motifs * n_regions)
    n_hits   = [0]   * (n_motifs * n_regions)
    sum_dens = [0.0] * (n_motifs * n_regions)

    for sr in sequences_by_region:
        for ri, region_name in enumerate(REGION_NAMES):
            seq = getattr(sr, region_name, "")
            if not seq:
                continue
            seq_len = len(seq)
            for mi, (compiled, pat_len) in enumerate(_COMPILED_MOTIFS):
                cell = mi * n_regions + ri
                n_totals[cell] += 1
                # Fast early exit: no density computation needed for misses
                if not compiled.search(seq):
                    continue
                n_hits[cell] += 1
                # Count overlapping occurrences for density
                count = 0
                pos = 0
                while True:
                    m = compiled.search(seq, pos)
                    if m is None:
                        break
                    count += 1
                    pos = m.start() + 1
                sum_dens[cell] += min(1.0, count * pat_len / seq_len)

    results: list[MotifRegionResult] = []
    for mi, (motif_name, protein, _) in enumerate(HNRNP_MOTIFS):
        for ri, region_name in enumerate(REGION_NAMES):
            cell = mi * n_regions + ri
            nt = n_totals[cell]
            results.append(MotifRegionResult(
                motif_name=motif_name,
                protein=protein,
                region=region_name,
                count_events_with_hit=n_hits[cell],
                total_events=nt,
                mean_density=sum_dens[cell] / nt if nt > 0 else 0.0,
            ))
    return results


def compare_groups(
    sig_results: list[MotifRegionResult],
    bg_results: list[MotifRegionResult],
) -> list[MotifEnrichmentResult]:
    """Compare motif enrichment between significant and background groups.

    For each (motif, region) pair, applies the standard pooled two-proportion
    z-test on binary hit presence (event hit / no-hit).  This is a large-sample
    normal approximation, not an exact test.

    Multiple-testing correction: Benjamini-Hochberg FDR across all testable
    (motif, region) pairs.  p_adjusted is the BH-adjusted q-value; significant
    is set to True when q < 0.05.
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

    # Benjamini-Hochberg FDR correction over all testable pairs
    testable = [r for r in raw if r.p_value is not None]
    if testable:
        p_raw = [r.p_value for r in testable]  # type: ignore[misc]
        q_values = _bh_adjust(p_raw)
        for r, q in zip(testable, q_values):
            r.p_adjusted = round(q, 6)
            r.significant = q < 0.05
    for r in raw:
        if r.p_adjusted is None:
            r.significant = False

    return raw


# ──────────────────────────────────────────────────────────────────────────────
# Stats helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bh_adjust(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR adjustment.

    Returns q-values in the same order as the input.  BH adjusted p-values
    are computed by sorting ascending on raw p-value, applying the BH scale
    factor at each rank, then enforcing monotonicity via a cumulative minimum
    scanned from the largest rank back to the smallest (q[rank i] <= q[rank i+1]).
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adjusted = [0.0] * n
    for rank, idx in enumerate(order, start=1):
        adjusted[idx] = p_values[idx] * n / rank
    # Enforce monotonicity: cumulative minimum from largest rank back to smallest
    min_q = 1.0
    for idx in reversed(order):
        min_q = min(min_q, adjusted[idx])
        adjusted[idx] = min_q
    return adjusted


def _proportion_z_test(
    k1: int, n1: int, k2: int, n2: int,
) -> tuple[float | None, float | None]:
    """Standard pooled two-proportion z-test for H0: p1 = p2.

    Returns (z_stat, raw_p_value) or (None, None) when the test is undefined.
    This is a large-sample normal approximation; caller is responsible for
    multiple-testing correction.
    """
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
    """Standard normal CDF via the identity Phi(x) = 0.5 * erfc(-x / sqrt(2)).

    The identity is mathematically exact; the numerical result depends on the
    precision of math.erfc (Python's C-library implementation), not on any
    hand-coded approximation.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2))
