"""
Splice features computation
============================
Derives splice-signal metrics from the three sequence windows returned by
``sequence.get_splice_windows``, plus the raw rMATS coordinates.

Features computed
-----------------
Sizes:
  exon_size              = exon_end - exon_start
  upstream_intron_size   = exon_start - upstream_ee   (+ strand convention)
  downstream_intron_size = downstream_es - exon_end

GT-AG canonical rule:
  donor_is_gt    donor_seq[3:5] == "GT"
  acceptor_is_ag acceptor_seq[17:19] == "AG"   (pos 17-18 in the 23-nt acceptor)

PPT (polypyrimidine tract):
  ppt_score       fraction of C/T in the 47-nt ppt_seq
  ppt_longest_run longest consecutive run of C or T

Branch-point (YNYURAY rule-based):
  Search the ppt_seq for the 7-mer Y-N-Y-T-R-A-Y.
  Position scoring (0-7): each base earns 1 point if it matches.
  N position always scores 1.
  Report best match if score >= 4.
  bp_distance = distance of the best motif centre from the 3'-most end of ppt_seq
                (≈ distance to 3'SS).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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


def find_branch_point(seq: str) -> tuple[int, int, int]:
    """Search *seq* for the best YNYURAY match.

    Returns
    -------
    (best_pos, best_score, best_distance)
    best_pos      : 0-based index of the first nt of the match in *seq*
    best_score    : 0-7 (7 = perfect)
    best_distance : distance from the last nt of seq (≈ distance to 3'SS)
    """
    upper = seq.upper()
    n = len(upper)
    best_pos, best_score = -1, 0
    for i in range(n - 6):
        motif = upper[i : i + 7]
        score = sum(fn(b) for fn, b in zip(_BP_CHECKS, motif))
        if score > best_score:
            best_score = score
            best_pos = i
    if best_pos < 0:
        return -1, 0, -1
    best_distance = n - (best_pos + 3)  # distance from motif centre to end of seq
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
    # sequences
    donor_seq: str = ""
    acceptor_seq: str = ""
    ppt_seq: str = ""
    # GT-AG
    donor_is_gt: bool | None = None
    acceptor_is_ag: bool | None = None
    # PPT
    ppt_score: float | None = None
    ppt_longest_run: int | None = None
    # branch-point
    bp_motif_found: bool = False
    bp_distance: int | None = None
    bp_score: int | None = None
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

    res = SpliceFeatureResult()

    # Sizes (no FASTA required)
    if exon_start is not None and exon_end is not None:
        res.exon_size = int(exon_end) - int(exon_start)
    if upstream_ee is not None and exon_start is not None:
        us = int(exon_start) - int(upstream_ee)
        res.upstream_intron_size = us if us >= 0 else None
    if downstream_es is not None and exon_end is not None:
        ds = int(downstream_es) - int(exon_end)
        res.downstream_intron_size = ds if ds >= 0 else None

    if windows is None:
        return res

    # Sequences
    res.donor_seq    = windows.donor_seq
    res.acceptor_seq = windows.acceptor_seq
    res.ppt_seq      = windows.ppt_seq

    # GT-AG
    d = windows.donor_seq.upper()
    a = windows.acceptor_seq.upper()
    res.donor_is_gt    = (len(d) >= 5 and d[3:5] == "GT")
    res.acceptor_is_ag = (len(a) >= 20 and a[17:19] == "AG")

    # PPT
    if windows.ppt_seq:
        res.ppt_score = round(ppt_score(windows.ppt_seq), 4)
        res.ppt_longest_run = longest_y_run(windows.ppt_seq)

    # Branch-point
    if windows.ppt_seq:
        bp_pos, bp_s, bp_dist = find_branch_point(windows.ppt_seq)
        res.bp_motif_found = bp_s >= 5          # at least 5/7 positions match
        res.bp_distance    = bp_dist if bp_s >= 5 else None
        res.bp_score       = bp_s

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
        total = len(col) or 1
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
        from collections import Counter
        counts = Counter(s[i].upper() for s in seqs if i < len(s))
        total = sum(counts.values()) or 1
        present = frozenset(b for b, c in counts.items() if c / total >= threshold)
        consensus.append(_IUPAC.get(present, "N"))
    return "".join(consensus)
