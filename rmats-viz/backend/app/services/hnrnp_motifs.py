"""
hnRNP motif enrichment analysis
=================================
Inspired by rMAPS2 (Hwang et al., NAR 2020), this module scans genomic
regions around skipped-exon (SE) events for known hnRNP RNA-binding
protein motifs and compares their frequency between significant (regulated)
and non-significant (background) events.

Methodology
-----------
For each SE event, seven regions are defined (transcript orientation):

  upstream exon ── [5'SS window ··· 3'SS window] ── [skipped exon] ── [5'SS window ··· 3'SS window] ── downstream exon
                    upstream intron                                    downstream intron

Region extraction follows the rMAPS2 design (Hwang 2020): every intron is
scanned at *both* ends, 250 nt after its 5' splice site and 250 nt before
its 3' splice site, excluding the first 6 nt after the 5'SS (GURAGU donor
signal) and the last 20 nt before the 3'SS (branch point / polypyrimidine
tract / AG acceptor signal).  With ``_FLANK_LEN = 250``, ``_FIVE_SS_EXCL = 6``
and ``_THREE_SS_EXCL = 20`` the seven regions are, in transcript order
(half-open intervals; "5'SS" and "3'SS" are the donor and acceptor of the
intron being described):

  1. upstream_exon           last min(len, 250) nt of the upstream exon
  2. upstream_intron_5ss     [5'SS + 6, min(5'SS + 6 + 250, 3'SS - 20))  of the upstream intron
  3. upstream_intron_3ss     [max(3'SS - 20 - 250, 5'SS + 6), 3'SS - 20)  of the upstream intron
  4. skipped_exon            full exon body
  5. downstream_intron_5ss   [5'SS + 6, min(5'SS + 6 + 250, 3'SS - 20))  of the downstream intron
  6. downstream_intron_3ss   [max(3'SS - 20 - 250, 5'SS + 6), 3'SS - 20)  of the downstream intron
  7. downstream_exon         first min(len, 250) nt of the downstream exon

The two windows of one intron are clipped to the intron body minus the two
exclusion zones.  For introns shorter than 6 + 250 + 250 + 20 = 526 nt the
5'SS and 3'SS windows therefore **overlap** (the same nucleotides are scanned
twice, once in each window; e.g. a 300-nt intron gives a 250-nt 5'SS window
and a 250-nt 3'SS window sharing 224 nt).  This is intentional and mirrors
rMAPS2, which also scans each intron end independently; the two windows of
one intron are not independent tests and should be read together.  When an
intron is at most 26 nt long, both windows are empty.

Strand handling: rMATS coordinates are always genomic (``upstream_*`` = lower
coordinates).  On the − strand the transcript-sense upstream exon is the
rMATS *downstream* exon, the 5'SS of every intron is at its genomic *high*
end and the 3'SS at its genomic *low* end; the windows are mirrored
accordingly (see :func:`define_se_regions`).  BED regions are returned in
genomic (+ strand) coordinates and the caller reverse-complements the
extracted sequences on the − strand.

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
  - motif density per event = (# overlapping occurrences × motif_length) /
    region_length, capped at 1 (0 when the motif is absent)
  - Presence test: a standard pooled two-proportion z-test on binary hit
    presence (event hit / no-hit) between significant and background groups.
    This is a large-sample normal approximation; it is only run when both
    groups contain at least 5 events.
  - Density test: a Mann-Whitney U test (normal approximation with tie
    correction, no continuity correction) on the per-event densities of the
    two groups.  Presence saturates for short motifs (AGG, GGG, TTTT, CTCT
    are present in almost every 250-nt window of both groups), whereas the
    density still discriminates; rMAPS2 uses the same rank test on
    per-window densities.
  - Raw p-values of each test family are adjusted separately across all
    testable (motif × region) pairs with the Benjamini-Hochberg FDR
    procedure (applied to the unrounded p-values).  A pair is called
    significant at q < 0.05 (expected FDR ≤ 5 %).  BH is preferred over
    Bonferroni for this exploratory screen because it controls the
    proportion of false positives among discoveries rather than the
    probability of any false positive in the family.

Note
----
rMAPS2 additionally slides a 50-bp window along each region and separates
events into up-regulated, down-regulated and background groups.  The
sliding-window positional map is not implemented here.

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
- Mann HB & Whitney DR. Ann Math Stat 1947; 18:50-60
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

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

# Seven regions, in transcript order (see module docstring).
REGION_NAMES = [
    "upstream_exon",
    "upstream_intron_5ss",
    "upstream_intron_3ss",
    "skipped_exon",
    "downstream_intron_5ss",
    "downstream_intron_3ss",
    "downstream_exon",
]

# ──────────────────────────────────────────────────────────────────────────────
# Regulatory effect annotations (ESE/ESS/ISE/ISS)
# ──────────────────────────────────────────────────────────────────────────────
# For each protein family × region pair, the *established* regulatory effect
# when the motif is enriched in that region.  Only assignments supported by
# strong, replicated published evidence are included; uncertain or context-
# dependent cases are None.  The published evidence is resolved at the level
# of the whole intron (upstream vs downstream), so the label of an intron is
# applied to both of its windows (5'SS-proximal and 3'SS-proximal).
#
# Sources:
#   hnRNP A1/A2 — Zhu et al., Mol Cell 2001; Damgaard et al., EMBO J 2002;
#     Kashima et al., Nat Genet 2007 (SMN2 ISS-N1)
#   hnRNP F/H — Martinez-Contreras et al., PLoS Biol 2006; Chen et al.,
#     Genes Dev 1999 (β-tropomyosin ESS); Erkelenz et al., Genome Biol 2013
#   hnRNP C — König et al., Nat Struct Mol Biol 2010 (iCLIP); Zarnack et al.,
#     Cell 2013 (Alu exonisation)
#   hnRNP L — House & Lynch, EMBO J 2006 (CD45 ESS); Hui et al., EMBO J 2005
#   hnRNP M — Huelga et al., Cell Rep 2012 (CLIP-seq)
#   PTB — Xue et al., Mol Cell 2009 (CLIP, RNA map); Wagner & Garcia-Blanco,
#     Mol Cell Biol 2001
#   PCBP1/E1, PCBP2/E2, hnRNP K — insufficient position-specific splicing
#     data; primarily characterised for mRNA stability / translation.
#
# Compact form: { protein_family: (upstream_exon, upstream_intron, skipped_exon,
#                                  downstream_intron, downstream_exon) }
_REGULATORY_EFFECTS_BY_ZONE: dict[str, tuple[str | None, ...]] = {
    "hnRNP A1/A2":      ("ESS", "ISS", "ESS", "ISS", "ESS"),
    "hnRNP E1 (PCBP1)": (None,  None,  None,  None,  None),
    "hnRNP E2 (PCBP2)": (None,  None,  None,  None,  None),
    "hnRNP F/H":        ("ESS", None,  "ESS", "ISE", "ESS"),
    "hnRNP K":          (None,  None,  None,  None,  None),
    "hnRNP C":          (None,  "ISE", "ESS", None,  None),
    "hnRNP L":          (None,  None,  "ESS", None,  None),
    "hnRNP M":          (None,  None,  "ESS", "ISS", None),
    "PTB (hnRNP I)":    (None,  "ISS", "ESS", "ISS", None),
}

# Format: { protein_family: { region: "ESS"|"ESE"|"ISS"|"ISE"|None } }
REGULATORY_EFFECTS: dict[str, dict[str, str | None]] = {
    protein: {
        "upstream_exon":         up_ex,
        "upstream_intron_5ss":   up_in,
        "upstream_intron_3ss":   up_in,
        "skipped_exon":          sk_ex,
        "downstream_intron_5ss": dn_in,
        "downstream_intron_3ss": dn_in,
        "downstream_exon":       dn_ex,
    }
    for protein, (up_ex, up_in, sk_ex, dn_in, dn_ex) in _REGULATORY_EFFECTS_BY_ZONE.items()
}

# Intronic exclusion zones (per rMAPS2): 6 nt at 5'SS, 20 nt at 3'SS
_FIVE_SS_EXCL = 6
_THREE_SS_EXCL = 20
# Max region length to extract for flanking exons / intron windows
_FLANK_LEN = 250

# Minimum group size for the normal-approximation tests (presence z-test and
# Mann-Whitney U); below this the approximations are unreliable.
_MIN_GROUP_SIZE = 5


# ──────────────────────────────────────────────────────────────────────────────
# Region extraction
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SERegions:
    """Seven genomic regions around a skipped exon for motif scanning.

    Sequences are in transcript orientation (already reverse-complemented on
    the − strand by the caller); an unavailable region is the empty string.
    """
    upstream_exon: str = ""
    upstream_intron_5ss: str = ""
    upstream_intron_3ss: str = ""
    skipped_exon: str = ""
    downstream_intron_5ss: str = ""
    downstream_intron_3ss: str = ""
    downstream_exon: str = ""


_Region = tuple[str, int, int]


def _intron_windows(chrom: str, lo: int, hi: int, strand: str) -> tuple[_Region, _Region]:
    """Return the (5'SS-proximal, 3'SS-proximal) windows of the intron [lo, hi).

    + strand: the 5'SS is at ``lo`` and the 3'SS at ``hi``.
    − strand: the 5'SS is at ``hi`` and the 3'SS at ``lo`` (mirror image).
    Each window is at most ``_FLANK_LEN`` nt and is clipped to the intron body
    minus the 6-nt donor and 20-nt acceptor exclusion zones; the two windows
    may overlap in short introns and are both empty when the body is ≤ 26 nt.
    """
    empty: _Region = (chrom, 0, 0)
    if strand == "+":
        body_lo = lo + _FIVE_SS_EXCL       # first scanned nt after the donor
        body_hi = hi - _THREE_SS_EXCL      # one past the last scanned nt before the acceptor
        five = (chrom, body_lo, min(body_lo + _FLANK_LEN, body_hi))
        three = (chrom, max(body_hi - _FLANK_LEN, body_lo), body_hi)
    else:
        body_hi = hi - _FIVE_SS_EXCL       # donor is at the genomic high end
        body_lo = lo + _THREE_SS_EXCL      # acceptor is at the genomic low end
        five = (chrom, max(body_hi - _FLANK_LEN, body_lo), body_hi)
        three = (chrom, body_lo, min(body_lo + _FLANK_LEN, body_hi))
    five = five if five[2] > five[1] else empty
    three = three if three[2] > three[1] else empty
    return five, three


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
    """Return the seven (chrom, start, end) BED regions in ``REGION_NAMES`` order.

    Coordinates are always genomic (+ strand, 0-based, half-open).  The caller
    reverse-complements the extracted sequences when ``strand == '-'``.  An
    unavailable region (missing flanking coordinate, or intron consumed by the
    exclusion zones) is returned as ``(chrom, 0, 0)``.

    Strand conventions:
    rMATS ALWAYS uses genomic ordering: upstream_* = lower coords, downstream_* = higher coords.
    True genomic layout for both strands:
      [upstream_es … upstream_ee) ── intron A ── [exon_start … exon_end) ── intron B ── [downstream_es … downstream_ee)

    + strand: transcript upstream exon = rMATS upstream exon; the transcript
              upstream intron is intron A (5'SS at upstream_ee, 3'SS at exon_start)
              and the downstream intron is intron B (5'SS at exon_end, 3'SS at downstream_es).
    − strand: transcript upstream exon = rMATS *downstream* exon (higher coords);
              the transcript upstream intron is intron B (5'SS at downstream_es,
              3'SS at exon_end) and the downstream intron is intron A (5'SS at
              exon_start, 3'SS at upstream_ee).  Each window is the mirror image
              of the + strand one (see :func:`_intron_windows`).
    """
    empty: _Region = (chrom, 0, 0)

    def _exon_tail(es: int | None, ee: int | None) -> _Region:
        """Last min(len, 250) nt of an exon whose intron-proximal end is ``ee``."""
        if es is None or ee is None:
            return empty
        take = min(ee - es, _FLANK_LEN)
        return (chrom, ee - take, ee)

    def _exon_head(es: int | None, ee: int | None) -> _Region:
        """First min(len, 250) nt of an exon whose intron-proximal end is ``es``."""
        if es is None or ee is None:
            return empty
        take = min(ee - es, _FLANK_LEN)
        return (chrom, es, es + take)

    # Intron A = [upstream_ee, exon_start), intron B = [exon_end, downstream_es)
    intron_a = (
        _intron_windows(chrom, upstream_ee, exon_start, strand)
        if upstream_ee is not None else (empty, empty)
    )
    intron_b = (
        _intron_windows(chrom, exon_end, downstream_es, strand)
        if downstream_es is not None else (empty, empty)
    )
    skipped: _Region = (chrom, exon_start, exon_end)

    if strand == "+":
        upstream_exon = _exon_tail(upstream_es, upstream_ee)
        up_5ss, up_3ss = intron_a
        dn_5ss, dn_3ss = intron_b
        downstream_exon = _exon_head(downstream_es, downstream_ee)
    else:
        # Transcript upstream exon is the rMATS downstream exon; its
        # intron-proximal end is downstream_es (genomic low boundary).
        upstream_exon = _exon_head(downstream_es, downstream_ee)
        up_5ss, up_3ss = intron_b
        dn_5ss, dn_3ss = intron_a
        # Transcript downstream exon is the rMATS upstream exon; its
        # intron-proximal end is upstream_ee (genomic high boundary).
        downstream_exon = _exon_tail(upstream_es, upstream_ee)

    return [upstream_exon, up_5ss, up_3ss, skipped, dn_5ss, dn_3ss, downstream_exon]


# ──────────────────────────────────────────────────────────────────────────────
# Motif scanning
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MotifRegionResult:
    """Motif scan result for one motif in one region across a group of events.

    ``densities`` holds one value per event with a non-empty region (0.0 when
    the motif is absent); ``mean_density`` is its mean.
    """
    motif_name: str
    protein: str
    region: str
    count_events_with_hit: int = 0
    total_events: int = 0
    mean_density: float = 0.0
    densities: list[float] = field(default_factory=list)


@dataclass
class MotifEnrichmentResult:
    """Comparison of one motif in one region: significant vs background.

    ``z_stat``/``p_value``/``p_adjusted``/``significant`` describe the
    presence (two-proportion z) test; ``density_*`` the Mann-Whitney U test on
    per-event densities.  Both p-value families are BH-adjusted separately.
    """
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
    density_u_stat: float | None = None
    density_p_value: float | None = None
    density_p_adjusted: float | None = None
    density_significant: bool = False


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
    - Per-event densities are kept (one float per motif × region × event)
      because the density test in :func:`compare_groups` is rank-based;
      misses append the shared ``0.0`` constant, so only hits allocate.
    """
    n_motifs = len(HNRNP_MOTIFS)
    n_regions = len(REGION_NAMES)

    # Flat pre-allocated accumulators: index = mi * n_regions + ri
    n_hits = [0] * (n_motifs * n_regions)
    densities: list[list[float]] = [[] for _ in range(n_motifs * n_regions)]

    for sr in sequences_by_region:
        for ri, region_name in enumerate(REGION_NAMES):
            seq = getattr(sr, region_name, "")
            if not seq:
                continue
            seq_len = len(seq)
            for mi, (compiled, pat_len) in enumerate(_COMPILED_MOTIFS):
                cell = mi * n_regions + ri
                # Fast early exit: no density computation needed for misses
                m = compiled.search(seq)
                if m is None:
                    densities[cell].append(0.0)
                    continue
                n_hits[cell] += 1
                # Count overlapping occurrences for density
                count = 0
                while m is not None:
                    count += 1
                    m = compiled.search(seq, m.start() + 1)
                densities[cell].append(min(1.0, count * pat_len / seq_len))

    results: list[MotifRegionResult] = []
    for mi, (motif_name, protein, _) in enumerate(HNRNP_MOTIFS):
        for ri, region_name in enumerate(REGION_NAMES):
            cell = mi * n_regions + ri
            dens = densities[cell]
            nt = len(dens)
            results.append(MotifRegionResult(
                motif_name=motif_name,
                protein=protein,
                region=region_name,
                count_events_with_hit=n_hits[cell],
                total_events=nt,
                mean_density=math.fsum(dens) / nt if nt > 0 else 0.0,
                densities=dens,
            ))
    return results


def compare_groups(
    sig_results: list[MotifRegionResult],
    bg_results: list[MotifRegionResult],
) -> list[MotifEnrichmentResult]:
    """Compare motif enrichment between significant and background groups.

    For each (motif, region) pair present in both groups:
    - presence test: pooled two-proportion z-test on binary hit presence
      (large-sample normal approximation; None when either group has fewer
      than ``_MIN_GROUP_SIZE`` events or the pooled proportion is 0 or 1);
    - density test: Mann-Whitney U on the per-event densities (normal
      approximation with tie correction; same minimum group size).

    Multiple-testing correction: Benjamini-Hochberg FDR across all testable
    pairs, run separately for the two p-value families on the *unrounded*
    p-values; the reported p-values and q-values are then rounded to 6 dp.
    ``significant`` / ``density_significant`` are True when q < 0.05.
    """
    bg_lookup: dict[tuple[str, str], MotifRegionResult] = {
        (r.motif_name, r.region): r for r in bg_results
    }

    raw: list[MotifEnrichmentResult] = []
    p_presence: list[float | None] = []
    p_density: list[float | None] = []
    for sr in sig_results:
        br = bg_lookup.get((sr.motif_name, sr.region))
        if br is None:
            continue
        z, p = _proportion_z_test(
            sr.count_events_with_hit, sr.total_events,
            br.count_events_with_hit, br.total_events,
        )
        u, pu = _mann_whitney_u(sr.densities, br.densities)
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
            density_u_stat=round(u, 4) if u is not None else None,
            density_p_value=round(pu, 6) if pu is not None else None,
        ))
        p_presence.append(p)
        p_density.append(pu)

    # Benjamini-Hochberg FDR correction, one family per test, on unrounded p
    for r, q in zip(raw, _bh_adjust_optional(p_presence)):
        r.p_adjusted = round(q, 6) if q is not None else None
        r.significant = q is not None and q < 0.05
    for r, q in zip(raw, _bh_adjust_optional(p_density)):
        r.density_p_adjusted = round(q, 6) if q is not None else None
        r.density_significant = q is not None and q < 0.05

    return raw


# ──────────────────────────────────────────────────────────────────────────────
# Stats helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bh_adjust_optional(p_values: list[float | None]) -> list[float | None]:
    """BH-adjust the non-None entries, returning None where the input was None."""
    idx = [i for i, p in enumerate(p_values) if p is not None]
    out: list[float | None] = [None] * len(p_values)
    if idx:
        q_values = _bh_adjust([p_values[i] for i in idx])  # type: ignore[misc]
        for i, q in zip(idx, q_values):
            out[i] = q
    return out


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

    Returns (z_stat, raw_p_value) or (None, None) when the test is undefined:
    either group smaller than ``_MIN_GROUP_SIZE`` events (the normal
    approximation is unreliable), or pooled proportion of 0 or 1.
    Caller is responsible for multiple-testing correction.
    """
    if n1 < _MIN_GROUP_SIZE or n2 < _MIN_GROUP_SIZE:
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


def _mann_whitney_u(
    a: Sequence[float], b: Sequence[float],
) -> tuple[float | None, float | None]:
    """Two-sided Mann-Whitney U test for H0: the distributions of a and b are equal.

    Returns (U_a, raw_p_value), where U_a is the U statistic of sample *a*
    (number of (a_i, b_j) pairs with a_i > b_j, ties counting 1/2).  The
    p-value is the normal approximation with the tie correction of the
    variance (no continuity correction).  Returns (None, None) when either
    sample has fewer than ``_MIN_GROUP_SIZE`` values, and (U_a, 1.0) when all
    values are tied (zero variance → no evidence against H0).
    """
    n1, n2 = len(a), len(b)
    if n1 < _MIN_GROUP_SIZE or n2 < _MIN_GROUP_SIZE:
        return None, None
    combined = np.concatenate([
        np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64),
    ])
    n = n1 + n2
    # Average ranks (1-based) with ties: rank of a tied block = mean of its positions
    _, inverse, counts = np.unique(combined, return_inverse=True, return_counts=True)
    cum = np.cumsum(counts)
    avg_rank = cum - (counts - 1) / 2.0
    ranks = avg_rank[inverse.ravel()]
    r1 = float(ranks[:n1].sum())
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    tie_term = float(np.sum(counts.astype(np.float64) ** 3 - counts))
    var = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1)))
    if var <= 0:
        return u1, 1.0
    z = (u1 - mu) / math.sqrt(var)
    p = 2 * (1 - _normal_cdf(abs(z)))
    return u1, min(1.0, max(0.0, p))


def _normal_cdf(x: float) -> float:
    """Standard normal CDF via the identity Phi(x) = 0.5 * erfc(-x / sqrt(2)).

    The identity is mathematically exact; the numerical result depends on the
    precision of math.erfc (Python's C-library implementation), not on any
    hand-coded approximation.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2))
