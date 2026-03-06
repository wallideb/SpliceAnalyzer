"""
Sequence extraction service
============================
Extracts genomic sub-sequences from a locally indexed GRCh38 FASTA
using ``samtools faidx``.

Coordinate convention
---------------------
All input coordinates follow the rMATS / BED convention:
  - 0-based start (inclusive)
  - end (exclusive)
``samtools faidx`` expects 1-based inclusive → we add +1 to start.

Splice-site windows (per SE event)
------------------------------------
For a skipped exon [exon_start, exon_end) on strand + :

  donor (5'SS)    chr : exon_end-3   .. exon_end+6      →  3nt exon + GT + 4nt intron
  acceptor (3'SS) chr : exon_start-20 .. exon_start+3   → 20nt intron + AG + 3nt exon
  ppt_zone        chr : exon_start-50 .. exon_start-3   → 47nt upstream of acceptor

For strand - (positions are still genomic / + strand):
  donor (5'SS)    chr : exon_start-6  .. exon_start+3   → RC → 3nt exon + GT + 4nt intron
  acceptor (3'SS) chr : exon_end-3    .. exon_end+20    → RC → 20nt intron + AG + 3nt exon
  ppt_zone        chr : exon_end+3    .. exon_end+50    → RC → 47nt PPT region
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# Complement table
_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")


def reverse_complement(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def extract_region(
    chrom: str,
    start: int,
    end: int,
    strand: str = "+",
    fasta_path: str | None = None,
) -> str:
    """Fetch a genomic sub-sequence (0-based BED coords → 1-based samtools).

    Returns empty string on any error (FASTA not available, region out of
    bounds, samtools not found).  The caller must tolerate empty strings.
    """
    if end <= start:
        return ""
    fasta = fasta_path or settings.GRCH38_FASTA
    # samtools faidx region: 1-based inclusive
    region = f"{chrom}:{start + 1}-{end}"
    try:
        result = subprocess.run(
            [settings.SAMTOOLS_BIN, "faidx", fasta, region],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        lines = result.stdout.strip().split("\n")
        seq = "".join(ln for ln in lines if not ln.startswith(">")).upper()
        if strand == "-":
            seq = reverse_complement(seq)
        return seq
    except FileNotFoundError:
        logger.warning("samtools not found at '%s'", settings.SAMTOOLS_BIN)
    except subprocess.CalledProcessError as exc:
        logger.debug("samtools faidx failed for %s: %s", region, exc.stderr)
    except subprocess.TimeoutExpired:
        logger.warning("samtools timed out for %s", region)
    return ""


# ---------------------------------------------------------------------------
# Window definitions
# ---------------------------------------------------------------------------

@dataclass
class SpliceWindows:
    donor_seq: str      # 9 nt  : 3 exon + GT + 4 intron
    acceptor_seq: str   # 23 nt : 20 intron + AG + 3 exon
    ppt_seq: str        # 47 nt : upstream of 3'SS


def get_splice_windows(
    chrom: str,
    strand: str,
    exon_start: int,
    exon_end: int,
    fasta_path: str | None = None,
) -> SpliceWindows:
    """Extract the three splice-signal windows for one SE skipped exon."""
    fp = fasta_path or settings.GRCH38_FASTA

    if strand == "+":
        donor_seq = extract_region(chrom, exon_end - 3, exon_end + 6, "+", fp)
        acceptor_seq = extract_region(chrom, exon_start - 20, exon_start + 3, "+", fp)
        ppt_seq = extract_region(chrom, exon_start - 50, exon_start - 3, "+", fp)
    else:
        # − strand: donor is at the exon_start side (genomically lower)
        donor_seq = extract_region(chrom, exon_start - 6, exon_start + 3, "-", fp)
        # acceptor is at the exon_end side (genomically higher)
        acceptor_seq = extract_region(chrom, exon_end - 3, exon_end + 20, "-", fp)
        # PPT is genomically above exon_end (= upstream in transcript)
        ppt_seq = extract_region(chrom, exon_end + 3, exon_end + 50, "-", fp)

    return SpliceWindows(
        donor_seq=donor_seq,
        acceptor_seq=acceptor_seq,
        ppt_seq=ppt_seq,
    )


def fasta_available(fasta_path: str | None = None) -> bool:
    """Return True if the FASTA file and its index exist and samtools works."""
    import os
    fp = fasta_path or settings.GRCH38_FASTA
    if not os.path.isfile(fp) or not os.path.isfile(fp + ".fai"):
        return False
    try:
        subprocess.run(
            [settings.SAMTOOLS_BIN, "--version"],
            capture_output=True, timeout=5, check=True,
        )
        return True
    except Exception:
        return False
