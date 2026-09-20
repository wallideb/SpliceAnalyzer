"""
Splice features computation
============================
Derives splice-signal metrics from the three sequence windows returned by
``sequence.get_splice_windows``, plus the raw rMATS coordinates.

Features computed
-----------------
Sizes:
  exon_size              = exon_end - exon_start
  + strand:
    upstream_intron_size   = exon_start - upstream_ee
    downstream_intron_size = downstream_es - exon_end
  - strand (rMATS "upstream"=lower genomic coords=3′ in transcript;
             rMATS "downstream"=higher genomic coords=5′ in transcript):
    upstream_intron_size   = downstream_es - exon_end
    downstream_intron_size = exon_start - upstream_ee

GT-AG canonical rule:
  donor_is_gt    donor_seq[3:5] == "GT"
  acceptor_is_ag acceptor_seq[18:20] == "AG"   (pos 18-19 in the 23-nt acceptor)

PPT (polypyrimidine tract):
  ppt_score       fraction of C/T in the 47-nt ppt_seq
  ppt_longest_run longest consecutive run of C or T

Branch-point (YNYURAY rule-based):
  Search the ppt_seq for the 7-mer Y-N-Y-T-R-A-Y (the human branch-point
  consensus yUnAy of Gao et al. 2008 NAR 36:2257 extended to 7 nt).
  Position scoring (0-7): each base earns 1 point if it matches.
  N position always scores 1.  The branch adenosine (position 6 of the
  7-mer, 0-based index 5) is mandatory: candidates without an A there are
  never reported.
  Only candidates whose branch A lies 18-44 nt upstream of the exon start
  are considered (> 95 % of human branch points, Leman et al. 2020 BMC
  Genomics 21:86).  Report the best match if score >= 5 (≥ 5/7 positions
  match); ties are broken in favour of the candidate closest to the 3'SS.
  bp_distance = distance (nt) from the branch adenosine to the exon start
                (the ppt_seq window ends 3 nt before the exon, hence the
                ``offset_to_exon`` parameter of ``find_branch_point``).
  bp_position = 0-based index of the 7-mer in ppt_seq; bp_motif = the 7-mer.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.services.sequence import SpliceWindows

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PPT helpers
# ---------------------------------------------------------------------------

def ppt_score(seq: str) -> float:
    """Fraction of C + T in *seq*."""
    if not seq:
        return 0.0
    upper = seq.upper()
    return sum(1 for c in upper if c in "CT") / len(upper)


def ppt_t_content(seq: str) -> float:
    """Fraction of T (thymine) in *seq*."""
    if not seq:
        return 0.0
    upper = seq.upper()
    return sum(1 for c in upper if c == "T") / len(upper)


def ppt_c_content(seq: str) -> float:
    """Fraction of C (cytosine) in *seq*."""
    if not seq:
        return 0.0
    upper = seq.upper()
    return sum(1 for c in upper if c == "C") / len(upper)


def longest_y_run(seq: str) -> int:
    """Length of the longest consecutive C/T run."""
    best = cur = 0
    for c in seq.upper():
        if c in "CT":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# ---------------------------------------------------------------------------
# Branch-point (YNYURAY)
# ---------------------------------------------------------------------------

# Y=C/T, N=any, U→T in DNA, R=A/G, A=A, Y=C/T
_BP_CHECKS = [
    lambda b: b in "CT",   # Y  pos 0
    lambda b: True,         # N  pos 1
    lambda b: b in "CT",   # Y  pos 2
    lambda b: b == "T",    # T  pos 3  (U in RNA)
    lambda b: b in "AG",   # R  pos 4
    lambda b: b == "A",    # A  pos 5
    lambda b: b in "CT",   # Y  pos 6
]


# Distance window (nt) from the branch adenosine to the 3'SS exon start.
# Leman et al. 2020 (BMC Genomics 21:86) — genome-wide mapping of human
# branch points: > 95 % lie between −18 and −44 nt of the acceptor site.
# Consensus yUnAy (Gao et al. 2008, NAR 36:2257), with the branch A at the
# 6th position of the 7-mer YNYTRAY used here.
_BP_MIN_DISTANCE = 18
_BP_MAX_DISTANCE = 44
# 0-based index of the branch adenosine inside the 7-mer YNYTRAY
_BP_A_INDEX = 5
_BP_SCORE_THRESHOLD = 5


def find_branch_point(seq: str, offset_to_exon: int = 3) -> tuple[int, int, int]:
    """Search *seq* (the PPT window) for the best YNYTRAY branch-point match.

    Parameters
    ----------
    seq : sequence ending ``offset_to_exon`` nt before the 3'SS exon start
        (``ppt_seq`` spans [exon_start-50, exon_start-3), so the default is 3).
    offset_to_exon : number of nt between the last base of *seq* and the
        first base of the exon.

    Only candidates with an adenosine at the branch position (index 5 of the
    7-mer) and whose branch A lies ``_BP_MIN_DISTANCE``–``_BP_MAX_DISTANCE``
    nt upstream of the exon start are considered.  Among candidates the
    highest score wins; ties go to the candidate closest to the 3'SS
    (most 3′).

    Returns
    -------
    (best_pos, best_score, best_distance)
    best_pos      : 0-based index of the first nt of the 7-mer in *seq*
    best_score    : 0-7 (7 = perfect match); the A position always matches
    best_distance : distance (nt) from the branch adenosine to the exon start
    ``(-1, 0, -1)`` when no candidate lies in the distance window.
    """
    upper = seq.upper()
    n = len(upper)
    best_pos, best_score, best_distance = -1, 0, -1
    for i in range(n - 6):
        motif = upper[i : i + 7]
        if motif[_BP_A_INDEX] != "A":
            continue  # branch adenosine is mandatory
        distance = (n + offset_to_exon) - (i + _BP_A_INDEX)
        if distance < _BP_MIN_DISTANCE or distance > _BP_MAX_DISTANCE:
            continue
        score = sum(fn(b) for fn, b in zip(_BP_CHECKS, motif))
        # Scanning 5′→3′: a later candidate with an equal score is closer to
        # the 3'SS, so ">=" implements the tie-break towards the acceptor.
        if score >= best_score:
            best_score = score
            best_pos = i
            best_distance = distance
    if best_pos < 0:
        return -1, 0, -1
    return best_pos, best_score, best_distance


# ---------------------------------------------------------------------------
# Per-event feature object
# ---------------------------------------------------------------------------

@dataclass
class SpliceFeatureResult:
    # sizes
    exon_size: int | None = None
    upstream_intron_size: int | None = None
    downstream_intron_size: int | None = None
    # sequences (skipped exon splice sites)
    donor_seq: str = ""
    acceptor_seq: str = ""
    ppt_seq: str = ""
    # sequences (flanking exon splice sites)
    upstream_donor_seq: str = ""
    downstream_acceptor_seq: str = ""
    # GT-AG (skipped exon)
    donor_is_gt: bool | None = None
    acceptor_is_ag: bool | None = None
    # GT-AG (flanking exons)
    upstream_donor_is_gt: bool | None = None
    downstream_acceptor_is_ag: bool | None = None
    # PPT (T / C content are not persisted: the routers recompute them from
    # ``ppt_seq`` with ``ppt_t_content`` / ``ppt_c_content`` when needed)
    ppt_score: float | None = None
    ppt_longest_run: int | None = None
    # branch-point
    bp_motif_found: bool = False
    bp_distance: int | None = None      # branch A → exon start (nt)
    bp_score: int | None = None
    bp_position: int | None = None      # 0-based index of the 7-mer in ppt_seq
    bp_motif: str | None = None         # the matched 7-mer
    # error flag (FASTA not available or coords invalid)
    error: str | None = None


def compute_features(
    event: Any,
    windows: SpliceWindows | None = None,
) -> SpliceFeatureResult:
    """Compute all splice features for one event.

    *event* must expose the rMATS coordinate fields as attributes or dict keys.
    *windows* can be pre-fetched; if None the caller must have already set it.
    Pass a SpliceWindows with empty strings to get size-only computation.
    """
    def _get(obj: Any, *keys: str) -> Any:
        for k in keys:
            try:
                return getattr(obj, k)
            except AttributeError:
                pass
            try:
                return obj[k]
            except (KeyError, TypeError):
                pass
        return None

    exon_start    = _get(event, "exon_start")
    exon_end      = _get(event, "exon_end")
    upstream_ee   = _get(event, "upstream_ee")
    downstream_es = _get(event, "downstream_es")
    strand        = _get(event, "strand") or "+"

    res = SpliceFeatureResult()

    # Sizes (no FASTA required)
    if exon_start is not None and exon_end is not None:
        res.exon_size = int(exon_end) - int(exon_start)

    # Intron sizes are strand-dependent.
    # rMATS ALWAYS uses genomic ordering: upstream_* = lower genomic coords,
    # downstream_* = higher genomic coords, regardless of strand.
    # True genomic layout for both strands:
    #   [upstream_es … upstream_ee) — intron — [exon_start … exon_end) — intron — [downstream_es … downstream_ee)
    #
    # + strand: upstream exon is 5′ in transcript.
    #   upstream_intron_size   = exon_start - upstream_ee
    #   downstream_intron_size = downstream_es - exon_end
    #
    # - strand: rMATS "upstream" exon (lower genomic coords) is 3′ in transcript;
    #           rMATS "downstream" exon (higher genomic coords) is 5′ in transcript.
    #   upstream intron (5′ of skipped exon)   = between exon_end and downstream_es
    #   downstream intron (3′ of skipped exon) = between upstream_ee and exon_start
    #   upstream_intron_size   = downstream_es - exon_end
    #   downstream_intron_size = exon_start - upstream_ee
    if strand == "+":
        if upstream_ee is not None and exon_start is not None:
            us = int(exon_start) - int(upstream_ee)
            res.upstream_intron_size = us if us >= 0 else None
        if downstream_es is not None and exon_end is not None:
            ds = int(downstream_es) - int(exon_end)
            res.downstream_intron_size = ds if ds >= 0 else None
    else:
        # rMATS "downstream" exon (higher coords) is transcript-upstream for minus strand
        if downstream_es is not None and exon_end is not None:
            us = int(downstream_es) - int(exon_end)
            res.upstream_intron_size = us if us >= 0 else None
        # rMATS "upstream" exon (lower coords) is transcript-downstream for minus strand
        if upstream_ee is not None and exon_start is not None:
            ds = int(exon_start) - int(upstream_ee)
            res.downstream_intron_size = ds if ds >= 0 else None

    if windows is None:
        return res

    # Sequences
    res.donor_seq               = windows.donor_seq
    res.acceptor_seq            = windows.acceptor_seq
    res.ppt_seq                 = windows.ppt_seq
    res.upstream_donor_seq      = windows.upstream_donor_seq
    res.downstream_acceptor_seq = windows.downstream_acceptor_seq

    # GT-AG.  Windows truncated near a contig end (or missing) cannot be
    # evaluated: report None rather than a spurious False.
    d = windows.donor_seq.upper()
    a = windows.acceptor_seq.upper()
    res.donor_is_gt    = (d[3:5] == "GT")   if len(d) >= 5  else None
    res.acceptor_is_ag = (a[18:20] == "AG") if len(a) >= 20 else None

    # Flanking exon GT-AG
    ud = windows.upstream_donor_seq.upper()
    da = windows.downstream_acceptor_seq.upper()
    res.upstream_donor_is_gt       = (ud[3:5] == "GT")   if len(ud) >= 5  else None
    res.downstream_acceptor_is_ag  = (da[18:20] == "AG") if len(da) >= 20 else None

    # PPT
    if windows.ppt_seq:
        res.ppt_score = round(ppt_score(windows.ppt_seq), 4)
        res.ppt_longest_run = longest_y_run(windows.ppt_seq)

    # Branch-point.  ppt_seq = [exon_start-50, exon_start-3) → the window
    # ends 3 nt before the exon (offset_to_exon=3); bp_distance is measured
    # from the branch adenosine to the exon start.
    if windows.ppt_seq:
        bp_pos, bp_s, bp_dist = find_branch_point(windows.ppt_seq, offset_to_exon=3)
        found = bp_pos >= 0 and bp_s >= _BP_SCORE_THRESHOLD   # ≥ 5/7 positions match, A present
        res.bp_motif_found = found
        res.bp_distance    = bp_dist if found else None
        res.bp_score       = bp_s
        if found:
            res.bp_position = bp_pos
            res.bp_motif    = windows.ppt_seq[bp_pos : bp_pos + 7].upper()

    return res


# ---------------------------------------------------------------------------
# Aggregate (PWM + consensus) helpers — used by the patterns endpoint
# ---------------------------------------------------------------------------

def compute_pwm(seqs: list[str]) -> list[dict[str, float]]:
    """Position weight matrix (frequency) from equal-length sequences."""
    if not seqs:
        return []
    n = min(len(s) for s in seqs)
    bases = list("ACGT")
    result = []
    for i in range(n):
        col = [s[i].upper() for s in seqs if i < len(s)]
        # Denominator counts A/C/G/T only so the frequencies sum to 1 even
        # when the column contains N or other IUPAC characters.
        total = sum(1 for c in col if c in "ACGT") or 1
        result.append({b: round(col.count(b) / total, 4) for b in bases})
    return result


def iupac_consensus(seqs: list[str], threshold: float = 0.40) -> str:
    """IUPAC consensus string from a list of aligned sequences."""
    _IUPAC: dict[frozenset, str] = {
        frozenset("A"): "A", frozenset("C"): "C",
        frozenset("G"): "G", frozenset("T"): "T",
        frozenset("AG"): "R", frozenset("CT"): "Y",
        frozenset("AC"): "M", frozenset("GT"): "K",
        frozenset("GC"): "S", frozenset("AT"): "W",
        frozenset("ACG"): "V", frozenset("ACT"): "H",
        frozenset("AGT"): "D", frozenset("CGT"): "B",
        frozenset("ACGT"): "N",
    }
    if not seqs:
        return ""
    n = min(len(s) for s in seqs)
    consensus = []
    for i in range(n):
        counts = Counter(s[i].upper() for s in seqs if i < len(s))
        total = sum(counts.values()) or 1
        present = frozenset(b for b, c in counts.items() if c / total >= threshold)
        consensus.append(_IUPAC.get(present, "N"))
    return "".join(consensus)
