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
  upstream donor  chr : upstream_ee-3 .. upstream_ee+6  →  9nt window at upstream exon 5'SS
  dn. acceptor    chr : downstream_es-20 .. downstream_es+3 → 23nt at downstream exon 3'SS

For strand - (positions are still genomic / + strand; all sequences RC'd after fetch):
  rMATS uses genomic ordering: upstream_*=lower coords, downstream_*=higher coords.
  For minus strand the rMATS "downstream" exon (higher coords) is 5′ in transcript;
  the rMATS "upstream" exon (lower coords) is 3′ in transcript.
  donor (5'SS)    chr : exon_start-6  .. exon_start+3      → RC → 3nt exon + GT + 4nt intron
  acceptor (3'SS) chr : exon_end-3    .. exon_end+20       → RC → 20nt intron + AG + 3nt exon
  ppt_zone        chr : exon_end+3    .. exon_end+50       → RC → 47nt PPT region
  upstream donor  chr : downstream_es-6 .. downstream_es+3 → RC → 9nt at 5′ flanking exon 5'SS
                        (downstream_es = LOW boundary of rMATS downstream exon = intron junction)
  dn. acceptor    chr : upstream_ee-3  .. upstream_ee+20   → RC → 23nt at 3′ flanking exon 3'SS
                        (upstream_ee = HIGH boundary of rMATS upstream exon = intron junction)

MANE boundary correction
------------------------
rMATS exon coordinates come from the alignment annotation (GTF), which may
differ from the MANE Select transcript boundaries.  When a MANE exon overlaps
the rMATS skipped exon with different start/end, the MANE boundaries are used
for the skipped-exon splice-site windows (donor, acceptor, PPT).  Flanking
exon windows are NOT corrected because their boundaries are defined by junction
reads (always accurate).  This fixes cases like ERCC1 exon 8 on the minus
strand, where the rMATS exon_end differs from the MANE boundary by ~36 nt,
causing the 3'SS acceptor sequence to be extracted at the wrong position.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable
from dataclasses import dataclass

from app.config import settings
from app.services.mane import _ensembl_chrom

logger = logging.getLogger(__name__)

# Complement table — full IUPAC nucleotide code (upper + lower case).
#   A↔T  C↔G  U→A (RNA uracil treated as T)
#   R(AG)↔Y(CT)  S(CG)↔S  W(AT)↔W  K(GT)↔M(AC)
#   B(CGT)↔V(ACG)  D(AGT)↔H(ACT)  N↔N
_COMP = str.maketrans(
    "ACGTURYSWKMBDHVNacgturyswkmbdhvn",
    "TGCAAYRSWMKVHDBNtgcaayrswmkvhdbn",
)

# UCSC chr-style → GRCh38 RefSeq accession (for NCBI-headered FASTA files)
_UCSC_TO_REFSEQ: dict[str, str] = {
    "chr1":  "NC_000001.11", "chr2":  "NC_000002.12", "chr3":  "NC_000003.12",
    "chr4":  "NC_000004.12", "chr5":  "NC_000005.10", "chr6":  "NC_000006.12",
    "chr7":  "NC_000007.14", "chr8":  "NC_000008.11", "chr9":  "NC_000009.12",
    "chr10": "NC_000010.11", "chr11": "NC_000011.10", "chr12": "NC_000012.12",
    "chr13": "NC_000013.11", "chr14": "NC_000014.9",  "chr15": "NC_000015.10",
    "chr16": "NC_000016.10", "chr17": "NC_000017.11", "chr18": "NC_000018.10",
    "chr19": "NC_000019.10", "chr20": "NC_000020.11", "chr21": "NC_000021.9",
    "chr22": "NC_000022.11", "chrX":  "NC_000023.11", "chrY":  "NC_000024.10",
    "chrM":  "NC_012920.1",  "chrMT": "NC_012920.1",
}

# Cache: (fasta_path → contig set). Keyed by path so a FASTA swap is handled;
# also re-reads if the cache entry is empty (FASTA not yet assembled at startup).
_fai_cache: dict[str, set[str]] = {}

# Max samtools region args per subprocess call.
# Each region string is ~20 chars; 5 000 × 20 B = 100 KB — well within
# the Linux ARG_MAX of 2 MB. For 120 k SE events × 5 regions = 600 k
# regions this prevents an OSError: [Errno 7] Argument list too long.
_SAMTOOLS_CHUNK = 5_000


def _fai_contig_set(fasta_path: str) -> set[str]:
    """Return the set of contig names from the .fai index.

    Cached per fasta_path, but re-reads when the cached set is empty so that a
    FASTA assembled after the backend started is picked up on the next request.
    """
    import os
    cached = _fai_cache.get(fasta_path)
    if cached:          # non-empty hit → return immediately
        return cached
    fai = fasta_path + ".fai"
    if os.path.isfile(fai):
        with open(fai) as f:
            contigs = {line.split("\t")[0] for line in f if line.strip()}
        if contigs:
            _fai_cache[fasta_path] = contigs
            return contigs
    return set()


def _resolve_chrom(chrom: str, fasta_path: str) -> str | None:
    """Return the contig name as it appears in the FASTA index, or None if unknown.

    Handles two common cases:
    - rMATS uses UCSC names (chr1…chr22, chrX, chrY, chrM)
    - NCBI FASTA files use RefSeq accessions (NC_000001.11 …)

    Returns None when the contig is not present in the index so callers can
    skip the region instead of passing an invalid name to samtools (which would
    cause the entire subprocess call to fail with exit status 1).
    """
    contigs = _fai_contig_set(fasta_path)
    if not contigs:
        # Index not yet available; pass through and let samtools report the error
        return chrom
    if chrom in contigs:
        return chrom
    # Try RefSeq alias
    alias = _UCSC_TO_REFSEQ.get(chrom)
    if alias and alias in contigs:
        return alias
    # Contig is genuinely absent from this FASTA — skip it
    return None


def reverse_complement(seq: str) -> str:
    """Reverse-complement *seq* using the full IUPAC alphabet.

    Unknown characters are passed through unchanged; ``U`` is complemented
    as ``T`` (→ ``A``).
    """
    return seq.translate(_COMP)[::-1]


def _parse_faidx_output(text: str, n_expected: int) -> list[str]:
    """Parse the multi-FASTA text written by ``samtools faidx``.

    One sequence is appended for EVERY header line, including records with
    no sequence lines (``samtools faidx`` emits an empty record for a region
    beyond the contig end), so the i-th sequence always belongs to the i-th
    requested region.  If the number of records does not match *n_expected*
    the whole chunk is blanked (an error is logged) rather than returning
    sequences that could be assigned to the wrong regions.
    """
    seqs: list[str] = []
    current: list[str] = []
    seen_header = False
    for line in text.split("\n"):
        if line.startswith(">"):
            if seen_header:
                seqs.append("".join(current).upper())
            current = []
            seen_header = True
        elif line.strip():
            current.append(line.strip())
    if seen_header:
        seqs.append("".join(current).upper())

    if len(seqs) != n_expected:
        logger.error(
            "samtools faidx returned %d records for %d regions — "
            "blanking the chunk to avoid mis-assigned sequences",
            len(seqs), n_expected,
        )
        return [""] * n_expected
    return seqs


def _faidx_chunk(
    fasta: str,
    chunk_idx: list[int],
    sam_regions: list[str],
    out: list[str],
    invalid: list[str],
    timed_out: list[str] | None = None,
) -> bool:
    """Run ``samtools faidx`` for the regions at *chunk_idx*, filling *out*.

    On ``CalledProcessError`` or ``TimeoutExpired`` the chunk is split in
    halves and retried recursively down to single regions so that only the
    invalid (or individually timing-out) regions are blanked; rejected regions
    are collected in *invalid*, timed-out ones are counted in *timed_out*.

    Returns False when samtools itself is unavailable (callers stop).
    """
    if not chunk_idx:
        return True
    if timed_out is None:
        timed_out = []
    chunk_regions = [sam_regions[i] for i in chunk_idx]
    try:
        result = subprocess.run(
            [settings.SAMTOOLS_BIN, "faidx", fasta] + chunk_regions,
            capture_output=True,
            text=True,
            timeout=max(30, len(chunk_regions) // 100),
            check=True,
        )
    except FileNotFoundError as exc:
        logger.warning("samtools not found: %s", exc)
        return False
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        if len(chunk_idx) == 1:
            if isinstance(exc, subprocess.TimeoutExpired):
                timed_out.append(chunk_regions[0])
                logger.debug("samtools faidx timed out on region %s", chunk_regions[0])
            else:
                invalid.append(chunk_regions[0])
                logger.debug(
                    "samtools faidx rejected region %s (rc=%d): %s",
                    chunk_regions[0], exc.returncode,
                    exc.stderr.strip() if exc.stderr else "(no stderr)",
                )
            return True
        if isinstance(exc, subprocess.TimeoutExpired):
            logger.warning(
                "Batch samtools faidx timed out (%d regions, first=%s) — retrying in halves",
                len(chunk_regions), chunk_regions[0],
            )
        mid = len(chunk_idx) // 2
        if not _faidx_chunk(fasta, chunk_idx[:mid], sam_regions, out, invalid, timed_out):
            return False
        return _faidx_chunk(fasta, chunk_idx[mid:], sam_regions, out, invalid, timed_out)

    seqs = _parse_faidx_output(result.stdout, len(chunk_idx))
    for idx, seq in zip(chunk_idx, seqs):
        out[idx] = seq
    return True


def extract_regions_batch(
    regions: list[tuple[str, int, int]],
    fasta_path: str | None = None,
    progress: "Callable[[int], None] | None" = None,
) -> list[str]:
    """Extract multiple genomic regions with batched samtools calls.

    Parameters
    ----------
    regions : list of (chrom, start, end) tuples (0-based BED coords).
        A negative *start* is clamped to 0 (the returned sequence is then
        shorter than requested); regions with ``end <= start`` or an unknown
        contig yield an empty string.

    Returns a list of sequences in the same order as *regions* (empty string
    for invalid regions or on error).  Regions are processed in chunks of
    ``_SAMTOOLS_CHUNK``; when samtools rejects a chunk it is retried in
    halves so that only the offending regions are blanked.
    """
    if not regions:
        return []
    fasta = fasta_path or settings.GRCH38_FASTA
    # Build samtools region strings; skip regions with unknown contigs so a
    # single bad chromosome does not abort the entire chunk.
    sam_regions: list[str] = []
    for chrom, start, end in regions:
        if start < 0:
            start = 0
        if end <= start:
            sam_regions.append("")
            continue
        resolved = _resolve_chrom(chrom, fasta)
        if resolved is None:
            sam_regions.append("")  # unknown contig — skip silently
            continue
        sam_regions.append(f"{resolved}:{start + 1}-{end}")

    # Filter out empty regions
    valid_indices = [i for i, r in enumerate(sam_regions) if r]
    if not valid_indices:
        if progress is not None:
            progress(len(regions))
        return [""] * len(regions)

    out = [""] * len(regions)
    invalid: list[str] = []
    timed_out: list[str] = []

    # Process in chunks to stay within OS ARG_MAX limits.
    for chunk_start in range(0, len(valid_indices), _SAMTOOLS_CHUNK):
        chunk_idx = valid_indices[chunk_start : chunk_start + _SAMTOOLS_CHUNK]
        ok = _faidx_chunk(fasta, chunk_idx, sam_regions, out, invalid, timed_out)
        if progress is not None:
            # Report in input-region units: everything up to the last valid
            # index of this chunk (including skipped regions in between).
            progress(chunk_idx[-1] + 1 if ok else len(regions))
        if not ok:
            break  # samtools unavailable — nothing more to do
    if progress is not None:
        progress(len(regions))

    if timed_out:
        logger.warning(
            "samtools faidx timed out on %d of %d regions (blanked): %s%s",
            len(timed_out), len(valid_indices), ", ".join(timed_out[:10]),
            " ..." if len(timed_out) > 10 else "",
        )
    if invalid:
        preview = ", ".join(invalid[:10])
        logger.warning(
            "samtools faidx rejected %d of %d regions (blanked): %s%s",
            len(invalid), len(valid_indices), preview,
            " ..." if len(invalid) > 10 else "",
        )

    return out


# ---------------------------------------------------------------------------
# Window definitions
# ---------------------------------------------------------------------------

@dataclass
class SpliceWindows:
    donor_seq: str               # 9 nt  : 3 exon + GT + 4 intron  (skipped exon 5'SS)
    acceptor_seq: str            # 23 nt : 20 intron + AG + 3 exon  (skipped exon 3'SS)
    ppt_seq: str                 # 47 nt : upstream of 3'SS
    upstream_donor_seq: str = ""    # 9 nt  : upstream flanking exon 5'SS
    downstream_acceptor_seq: str = ""  # 23 nt : downstream flanking exon 3'SS
    source: str = "fasta"        # "fasta" | "ensembl"


# Fixed slot order used by every extraction path.
_WINDOW_KEYS: tuple[str, ...] = (
    "donor", "acceptor", "ppt", "upstream_donor", "downstream_acceptor",
)


def splice_window_coords(
    strand: str,
    se_start: int,
    se_end: int,
    upstream_es: int | None,
    upstream_ee: int | None,
    downstream_es: int | None,
    downstream_ee: int | None,
) -> dict[str, tuple[int, int] | None]:
    """Genomic 0-based half-open intervals of the five splice-signal windows.

    Pure function — the single definition of the window coordinates used by
    ``get_splice_windows``, ``get_splice_windows_batch`` and
    ``get_splice_windows_from_ensembl`` (see the module docstring for the
    rationale of each window).  All intervals are on the + genomic strand;
    sequences of − strand events must be reverse-complemented after fetching.

    Parameters
    ----------
    strand : "+" or "-"
    se_start, se_end : skipped exon (possibly MANE-corrected) boundaries
    upstream_es/ee, downstream_es/ee : rMATS flanking exon boundaries in
        GENOMIC order (upstream = lower coordinates, downstream = higher),
        regardless of strand.  ``upstream_es`` / ``downstream_ee`` are the
        outer boundaries and are not needed by any window; they are accepted
        so callers can pass the whole rMATS tuple.

    Returns
    -------
    dict with keys ``donor``, ``acceptor``, ``ppt``, ``upstream_donor``,
    ``downstream_acceptor`` → ``(start, end)`` or ``None`` when the flanking
    exon boundary the window depends on is missing.

    + strand:
      donor               [se_end-3,        se_end+6)
      acceptor            [se_start-20,     se_start+3)
      ppt                 [se_start-50,     se_start-3)
      upstream_donor      [upstream_ee-3,   upstream_ee+6)
      downstream_acceptor [downstream_es-20, downstream_es+3)
    − strand (rMATS "downstream" exon = 5′ flanking, "upstream" = 3′ flanking):
      donor               [se_start-6,      se_start+3)
      acceptor            [se_end-3,        se_end+20)
      ppt                 [se_end+3,        se_end+50)
      upstream_donor      [downstream_es-6, downstream_es+3)
      downstream_acceptor [upstream_ee-3,   upstream_ee+20)
    """
    if strand == "+":
        # Upstream flanking exon: donor (5'SS) is at the HIGH boundary (upstream_ee)
        # Downstream flanking exon: acceptor (3'SS) is at the LOW boundary (downstream_es)
        return {
            "donor":    (se_end - 3,    se_end + 6),
            "acceptor": (se_start - 20, se_start + 3),
            "ppt":      (se_start - 50, se_start - 3),
            "upstream_donor": (
                (upstream_ee - 3, upstream_ee + 6)
                if upstream_ee is not None else None
            ),
            "downstream_acceptor": (
                (downstream_es - 20, downstream_es + 3)
                if downstream_es is not None else None
            ),
        }
    # Minus strand: rMATS uses GENOMIC ordering (upstream_*=lower coords,
    # downstream_*=higher coords) regardless of strand.
    # The rMATS "downstream" exon (higher genomic coords) is the 5′ flanking
    # exon (transcript-upstream); its 5'SS donor is at downstream_es (LOW
    # boundary of that exon).  The rMATS "upstream" exon (lower genomic
    # coords) is the 3′ flanking exon (transcript-downstream); its 3'SS
    # acceptor is at upstream_ee (HIGH boundary of that exon).
    return {
        "donor":    (se_start - 6, se_start + 3),
        "acceptor": (se_end - 3,   se_end + 20),
        "ppt":      (se_end + 3,   se_end + 50),
        "upstream_donor": (
            (downstream_es - 6, downstream_es + 3)
            if downstream_es is not None else None
        ),
        "downstream_acceptor": (
            (upstream_ee - 3, upstream_ee + 20)
            if upstream_ee is not None else None
        ),
    }


def _windows_to_regions(
    chrom: str, coords: dict[str, tuple[int, int] | None]
) -> list[tuple[str, int, int]]:
    """Flatten window coords into the fixed 5-slot region list.

    Missing windows become the empty region ``(chrom, 0, 0)`` so the slot
    layout (and therefore the sequence order) is preserved.
    """
    return [
        (chrom, *coords[k]) if coords[k] is not None else (chrom, 0, 0)
        for k in _WINDOW_KEYS
    ]


def _build_windows(
    seqs: list[str],
    coords: dict[str, tuple[int, int] | None],
    need_rc: bool,
    source: str,
) -> SpliceWindows:
    """Assemble a SpliceWindows from the 5 fetched sequences (slot order)."""
    if need_rc:
        seqs = [reverse_complement(s) if s else "" for s in seqs]
    return SpliceWindows(
        donor_seq=seqs[0],
        acceptor_seq=seqs[1],
        ppt_seq=seqs[2],
        upstream_donor_seq=seqs[3] if coords["upstream_donor"] is not None else "",
        downstream_acceptor_seq=seqs[4] if coords["downstream_acceptor"] is not None else "",
        source=source,
    )


def get_splice_windows(
    chrom: str,
    strand: str,
    exon_start: int,
    exon_end: int,
    fasta_path: str | None = None,
    upstream_es: int | None = None,
    upstream_ee: int | None = None,
    downstream_es: int | None = None,
    downstream_ee: int | None = None,
    mane_exon_start: int | None = None,
    mane_exon_end: int | None = None,
) -> SpliceWindows:
    """Extract splice-signal windows for one SE skipped exon.

    All four flanking exon coordinates should be supplied (0-based BED):
      upstream_es / upstream_ee   — start/end of the upstream flanking exon
      downstream_es / downstream_ee — start/end of the downstream flanking exon

    Optional MANE-corrected exon boundaries:
      mane_exon_start / mane_exon_end — if supplied, these override the rMATS
      exon_start / exon_end for the skipped-exon splice-site windows (donor,
      acceptor, PPT).  This corrects cases where the rMATS annotation has
      different exon boundaries than the MANE Select transcript, causing
      splice-site sequences to be extracted at the wrong genomic position.

    The splice-site boundary used per strand (see ``splice_window_coords``):
      + strand: upstream donor at upstream_ee (high boundary)
                downstream acceptor at downstream_es (low boundary)
      - strand: upstream donor at downstream_es (low boundary of the 5′ flanking exon)
                downstream acceptor at upstream_ee (high boundary of the 3′ flanking exon)

    Uses a single batched samtools call for all 3-5 regions (1 subprocess
    instead of 5), which is ~4x faster per event.
    """
    fp = fasta_path or settings.GRCH38_FASTA
    need_rc = strand == "-"

    # Use MANE-corrected boundaries for the skipped exon splice sites if
    # available; fall back to the rMATS coordinates otherwise.
    se_start = mane_exon_start if mane_exon_start is not None else exon_start
    se_end   = mane_exon_end   if mane_exon_end   is not None else exon_end

    coords = splice_window_coords(
        strand, se_start, se_end,
        upstream_es, upstream_ee, downstream_es, downstream_ee,
    )
    # Regions are always fetched on + strand; RC applied afterwards if needed.
    seqs = extract_regions_batch(_windows_to_regions(chrom, coords), fp)
    return _build_windows(seqs, coords, need_rc, "fasta")


def get_splice_windows_batch(
    events: list[tuple[str, str, int, int, int | None, int | None, int | None, int | None]],
    fasta_path: str | None = None,
    mane_boundaries: list[tuple[int, int] | None] | None = None,
) -> list[SpliceWindows]:
    """Extract splice windows for many events in ONE samtools call.

    Parameters
    ----------
    events : list of
        (chrom, strand, exon_start, exon_end,
         upstream_es, upstream_ee, downstream_es, downstream_ee)
    mane_boundaries : optional list of (mane_exon_start, mane_exon_end) or None
        per event.  When provided and not None for a given event, the MANE
        exon boundaries are used instead of the rMATS exon_start/exon_end for
        the skipped-exon splice-site windows (donor, acceptor, PPT).

    The correct splice-site boundary is selected per strand (see
    ``splice_window_coords`` for the strand logic).

    Returns a list of SpliceWindows (same order as *events*).
    ~20-50x faster than calling get_splice_windows() per event because
    it spawns a single samtools subprocess for all regions.
    """
    if not events:
        return []
    fp = fasta_path or settings.GRCH38_FASTA

    # Build a flat region list: 5 regions per event, in slot order.
    all_regions: list[tuple[str, int, int]] = []
    event_meta: list[tuple[bool, dict[str, tuple[int, int] | None]]] = []

    for idx, (chrom, strand, exon_start, exon_end, upstream_es, upstream_ee, downstream_es, downstream_ee) in enumerate(events):
        need_rc = strand == "-"

        # Use MANE-corrected boundaries for the skipped exon splice sites if
        # available; fall back to the rMATS coordinates otherwise.
        mb = mane_boundaries[idx] if mane_boundaries and idx < len(mane_boundaries) else None
        se_start = mb[0] if mb is not None else exon_start
        se_end   = mb[1] if mb is not None else exon_end

        coords = splice_window_coords(
            strand, se_start, se_end,
            upstream_es, upstream_ee, downstream_es, downstream_ee,
        )
        event_meta.append((need_rc, coords))
        all_regions.extend(_windows_to_regions(chrom, coords))

    all_seqs = extract_regions_batch(all_regions, fp)

    # Unpack: 5 seqs per event
    n = len(_WINDOW_KEYS)
    return [
        _build_windows(all_seqs[i * n : i * n + n], coords, need_rc, "fasta")
        for i, (need_rc, coords) in enumerate(event_meta)
    ]


# ---------------------------------------------------------------------------
# Ensembl REST API fallback (no local FASTA required)
# ---------------------------------------------------------------------------

def _fetch_ensembl_seq(chrom: str, start: int, end: int) -> str:
    """Fetch a genomic sequence from Ensembl REST API (0-based BED → 1-based inclusive).

    Returns empty string on any error (network, quota, region out of bounds).
    """
    import json
    import urllib.request

    if end <= start:
        return ""

    # Convert UCSC-style chr names to Ensembl (strip 'chr', map M → MT)
    ens = _ensembl_chrom(chrom)

    region = f"{ens}:{start + 1}..{end}"
    url = (
        f"https://rest.ensembl.org/sequence/region/human/{region}"
        "?content-type=application/json"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rmats-viz/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())
            return data.get("seq", "").upper()
    except Exception as exc:
        logger.debug("Ensembl REST %s: %s", region, exc)
        return ""


def get_splice_windows_from_ensembl(
    chrom: str,
    strand: str,
    exon_start: int,
    exon_end: int,
    upstream_es: int | None = None,
    upstream_ee: int | None = None,
    downstream_es: int | None = None,
    downstream_ee: int | None = None,
    mane_exon_start: int | None = None,
    mane_exon_end: int | None = None,
) -> SpliceWindows:
    """Identical window definitions to get_splice_windows() via Ensembl REST API.

    Used as a fallback when no local FASTA/samtools is available.
    Makes up to 5 sequential HTTP calls (donor, acceptor, PPT, upstream donor, downstream acceptor).
    See ``splice_window_coords`` for the strand-specific boundary logic.
    """
    # Use MANE-corrected boundaries for the skipped exon splice sites if available.
    se_start = mane_exon_start if mane_exon_start is not None else exon_start
    se_end   = mane_exon_end   if mane_exon_end   is not None else exon_end

    coords = splice_window_coords(
        strand, se_start, se_end,
        upstream_es, upstream_ee, downstream_es, downstream_ee,
    )
    seqs = [
        _fetch_ensembl_seq(chrom, *coords[k]) if coords[k] is not None else ""
        for k in _WINDOW_KEYS
    ]
    return _build_windows(seqs, coords, strand == "-", "ensembl")


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
