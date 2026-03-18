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
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# Complement table
_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")

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
    return seq.translate(_COMP)[::-1]


def extract_regions_batch(
    regions: list[tuple[str, int, int]],
    fasta_path: str | None = None,
) -> list[str]:
    """Extract multiple genomic regions in a single samtools call.

    Parameters
    ----------
    regions : list of (chrom, start, end) tuples (0-based BED coords).

    Returns a list of sequences in the same order (empty string on error).
    Much faster than calling extract_region() N times for large batches.
    """
    if not regions:
        return []
    fasta = fasta_path or settings.GRCH38_FASTA
    # Build samtools region strings; skip regions with unknown contigs so a
    # single bad chromosome does not abort the entire chunk.
    sam_regions: list[str] = []
    for chrom, start, end in regions:
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
        return [""] * len(regions)

    out = [""] * len(regions)

    # Process in chunks to stay within OS ARG_MAX limits.
    for chunk_start in range(0, len(valid_indices), _SAMTOOLS_CHUNK):
        chunk_idx = valid_indices[chunk_start : chunk_start + _SAMTOOLS_CHUNK]
        chunk_regions = [sam_regions[i] for i in chunk_idx]
        try:
            result = subprocess.run(
                [settings.SAMTOOLS_BIN, "faidx", fasta] + chunk_regions,
                capture_output=True,
                text=True,
                timeout=max(30, len(chunk_regions) // 100),
                check=True,
            )
            # Parse multi-FASTA output for this chunk
            seqs: list[str] = []
            current: list[str] = []
            for line in result.stdout.split("\n"):
                if line.startswith(">"):
                    if current:
                        seqs.append("".join(current).upper())
                        current = []
                elif line.strip():
                    current.append(line.strip())
            if current:
                seqs.append("".join(current).upper())

            for idx, seq in zip(chunk_idx, seqs):
                out[idx] = seq
        except FileNotFoundError as exc:
            logger.warning("samtools not found: %s", exc)
        except subprocess.TimeoutExpired as exc:
            logger.warning("Batch samtools faidx timed out (chunk offset %d)", chunk_start)
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "Batch samtools faidx failed (chunk offset %d, rc=%d): %s",
                chunk_start, exc.returncode,
                exc.stderr.strip() if exc.stderr else "(no stderr)",
            )
            # Leave those chunk positions as "" and continue

    return out


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
    resolved = _resolve_chrom(chrom, fasta)
    if resolved is None:
        return ""
    # samtools faidx region: 1-based inclusive
    region = f"{resolved}:{start + 1}-{end}"
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
    donor_seq: str               # 9 nt  : 3 exon + GT + 4 intron  (skipped exon 5'SS)
    acceptor_seq: str            # 23 nt : 20 intron + AG + 3 exon  (skipped exon 3'SS)
    ppt_seq: str                 # 47 nt : upstream of 3'SS
    upstream_donor_seq: str = ""    # 9 nt  : upstream flanking exon 5'SS
    downstream_acceptor_seq: str = ""  # 23 nt : downstream flanking exon 3'SS
    source: str = "fasta"        # "fasta" | "ensembl"


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
) -> SpliceWindows:
    """Extract splice-signal windows for one SE skipped exon.

    All four flanking exon coordinates should be supplied (0-based BED):
      upstream_es / upstream_ee   — start/end of the upstream flanking exon
      downstream_es / downstream_ee — start/end of the downstream flanking exon

    The splice-site boundary used per strand:
      + strand: upstream donor at upstream_ee (high boundary)
                downstream acceptor at downstream_es (low boundary)
      - strand: upstream donor at upstream_es (low boundary, intron is 5' of it)
                downstream acceptor at downstream_ee (high boundary, intron is 3' of it)

    Uses a single batched samtools call for all 3-5 regions (1 subprocess
    instead of 5), which is ~4x faster per event.
    """
    fp = fasta_path or settings.GRCH38_FASTA
    need_rc = strand == "-"

    # Build region list in a fixed order: donor, acceptor, ppt, up_donor, dn_acceptor
    # Regions are always fetched on + strand; RC applied afterwards if needed.
    # has_upstream_donor    : whether slot 3 (upstream_donor_seq) can be filled
    # has_downstream_acceptor: whether slot 4 (downstream_acceptor_seq) can be filled
    # Both are named from the transcript perspective (5'→3').
    regions: list[tuple[str, int, int]] = []
    if strand == "+":
        # Upstream flanking exon: donor (5'SS) is at the HIGH boundary (upstream_ee)
        # Downstream flanking exon: acceptor (3'SS) is at the LOW boundary (downstream_es)
        has_upstream_donor      = upstream_ee is not None
        has_downstream_acceptor = downstream_es is not None
        regions.append((chrom, exon_end - 3,    exon_end + 6))      # donor
        regions.append((chrom, exon_start - 20, exon_start + 3))    # acceptor
        regions.append((chrom, exon_start - 50, exon_start - 3))    # ppt
        regions.append(
            (chrom, upstream_ee - 3, upstream_ee + 6)
            if has_upstream_donor else (chrom, 0, 0)
        )
        regions.append(
            (chrom, downstream_es - 20, downstream_es + 3)
            if has_downstream_acceptor else (chrom, 0, 0)
        )
    else:
        # Minus strand: rMATS uses GENOMIC ordering (upstream_*=lower coords,
        # downstream_*=higher coords) regardless of strand.
        # For minus strand, the rMATS "downstream" exon (higher genomic coords)
        # is the 5′ flanking exon (transcript-upstream); its 5'SS donor is at
        # downstream_es (LOW boundary of that exon).
        # The rMATS "upstream" exon (lower genomic coords) is the 3′ flanking
        # exon (transcript-downstream); its 3'SS acceptor is at upstream_ee
        # (HIGH boundary of that exon).
        has_upstream_donor      = downstream_es is not None  # 5′ flanking exon (rMATS downstream)
        has_downstream_acceptor = upstream_ee is not None    # 3′ flanking exon (rMATS upstream)
        regions.append((chrom, exon_start - 6,  exon_start + 3))    # donor
        regions.append((chrom, exon_end - 3,    exon_end + 20))     # acceptor
        regions.append((chrom, exon_end + 3,    exon_end + 50))     # ppt
        regions.append(
            (chrom, downstream_es - 6, downstream_es + 3)
            if has_upstream_donor else (chrom, 0, 0)
        )
        regions.append(
            (chrom, upstream_ee - 3, upstream_ee + 20)
            if has_downstream_acceptor else (chrom, 0, 0)
        )

    seqs = extract_regions_batch(regions, fp)

    if need_rc:
        seqs = [reverse_complement(s) if s else "" for s in seqs]

    return SpliceWindows(
        donor_seq=seqs[0],
        acceptor_seq=seqs[1],
        ppt_seq=seqs[2],
        upstream_donor_seq=seqs[3] if has_upstream_donor else "",
        downstream_acceptor_seq=seqs[4] if has_downstream_acceptor else "",
        source="fasta",
    )


def get_splice_windows_batch(
    events: list[tuple[str, str, int, int, int | None, int | None, int | None, int | None]],
    fasta_path: str | None = None,
) -> list[SpliceWindows]:
    """Extract splice windows for many events in ONE samtools call.

    Parameters
    ----------
    events : list of
        (chrom, strand, exon_start, exon_end,
         upstream_es, upstream_ee, downstream_es, downstream_ee)

    The correct splice-site boundary is selected per strand (see
    get_splice_windows() docstring for the strand logic).

    Returns a list of SpliceWindows (same order as *events*).
    ~20-50x faster than calling get_splice_windows() per event because
    it spawns a single samtools subprocess for all regions.
    """
    if not events:
        return []
    fp = fasta_path or settings.GRCH38_FASTA

    # Build a flat region list: 5 regions per event, in order.
    # has_upstream_donor    : whether slot 3 (upstream_donor_seq) can be filled
    # has_downstream_acceptor: whether slot 4 (downstream_acceptor_seq) can be filled
    # Both are named from the transcript perspective (5'→3').
    all_regions: list[tuple[str, int, int]] = []
    event_meta: list[tuple[bool, bool, bool]] = []  # (need_rc, has_upstream_donor, has_downstream_acceptor)

    for chrom, strand, exon_start, exon_end, upstream_es, upstream_ee, downstream_es, downstream_ee in events:
        need_rc = strand == "-"
        if strand == "+":
            # Upstream flanking exon: donor (5'SS) is at the HIGH boundary (upstream_ee)
            # Downstream flanking exon: acceptor (3'SS) is at the LOW boundary (downstream_es)
            has_upstream_donor      = upstream_ee is not None
            has_downstream_acceptor = downstream_es is not None
        else:
            # Minus strand: rMATS "downstream" exon (higher coords) is 5′ flanking
            # (transcript-upstream); its 5'SS donor is at downstream_es.
            # rMATS "upstream" exon (lower coords) is 3′ flanking; its 3'SS
            # acceptor is at upstream_ee.
            has_upstream_donor      = downstream_es is not None  # 5′ flanking exon (rMATS downstream)
            has_downstream_acceptor = upstream_ee is not None    # 3′ flanking exon (rMATS upstream)
        event_meta.append((need_rc, has_upstream_donor, has_downstream_acceptor))

        if strand == "+":
            all_regions.append((chrom, exon_end - 3,    exon_end + 6))
            all_regions.append((chrom, exon_start - 20, exon_start + 3))
            all_regions.append((chrom, exon_start - 50, exon_start - 3))
            all_regions.append(
                (chrom, upstream_ee - 3, upstream_ee + 6)
                if has_upstream_donor else (chrom, 0, 0)
            )
            all_regions.append(
                (chrom, downstream_es - 20, downstream_es + 3)
                if has_downstream_acceptor else (chrom, 0, 0)
            )
        else:
            # Minus strand: upstream donor at downstream_es (LOW boundary of 5′ flanking exon)
            #               downstream acceptor at upstream_ee (HIGH boundary of 3′ flanking exon)
            all_regions.append((chrom, exon_start - 6,  exon_start + 3))
            all_regions.append((chrom, exon_end - 3,    exon_end + 20))
            all_regions.append((chrom, exon_end + 3,    exon_end + 50))
            all_regions.append(
                (chrom, downstream_es - 6, downstream_es + 3)
                if has_upstream_donor else (chrom, 0, 0)
            )
            all_regions.append(
                (chrom, upstream_ee - 3, upstream_ee + 20)
                if has_downstream_acceptor else (chrom, 0, 0)
            )

    all_seqs = extract_regions_batch(all_regions, fp)

    # Unpack: 5 seqs per event
    results: list[SpliceWindows] = []
    for i, (need_rc, has_upstream_donor, has_downstream_acceptor) in enumerate(event_meta):
        seqs = all_seqs[i * 5 : i * 5 + 5]
        if need_rc:
            seqs = [reverse_complement(s) if s else "" for s in seqs]
        results.append(SpliceWindows(
            donor_seq=seqs[0],
            acceptor_seq=seqs[1],
            ppt_seq=seqs[2],
            upstream_donor_seq=seqs[3] if has_upstream_donor else "",
            downstream_acceptor_seq=seqs[4] if has_downstream_acceptor else "",
            source="fasta",
        ))

    return results


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
    ens = chrom[3:] if chrom.startswith("chr") else chrom
    if ens == "M":
        ens = "MT"

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
) -> SpliceWindows:
    """Identical window definitions to get_splice_windows() via Ensembl REST API.

    Used as a fallback when no local FASTA/samtools is available.
    Makes up to 5 sequential HTTP calls (donor, acceptor, PPT, upstream donor, downstream acceptor).
    See get_splice_windows() for the strand-specific boundary logic.
    """
    if strand == "+":
        donor_seq    = _fetch_ensembl_seq(chrom, exon_end - 3,    exon_end + 6)
        acceptor_seq = _fetch_ensembl_seq(chrom, exon_start - 20, exon_start + 3)
        ppt_seq      = _fetch_ensembl_seq(chrom, exon_start - 50, exon_start - 3)
        upstream_donor_seq = (
            _fetch_ensembl_seq(chrom, upstream_ee - 3, upstream_ee + 6)
            if upstream_ee is not None else ""
        )
        downstream_acceptor_seq = (
            _fetch_ensembl_seq(chrom, downstream_es - 20, downstream_es + 3)
            if downstream_es is not None else ""
        )
    else:
        # Minus strand: rMATS "downstream" exon (higher coords) is 5′ flanking.
        # upstream donor at downstream_es (LOW boundary of 5′ flanking exon)
        # downstream acceptor at upstream_ee (HIGH boundary of 3′ flanking exon)
        donor_seq    = reverse_complement(_fetch_ensembl_seq(chrom, exon_start - 6, exon_start + 3))
        acceptor_seq = reverse_complement(_fetch_ensembl_seq(chrom, exon_end - 3,   exon_end + 20))
        ppt_seq      = reverse_complement(_fetch_ensembl_seq(chrom, exon_end + 3,   exon_end + 50))
        upstream_donor_seq = (
            reverse_complement(_fetch_ensembl_seq(chrom, downstream_es - 6, downstream_es + 3))
            if downstream_es is not None else ""
        )
        downstream_acceptor_seq = (
            reverse_complement(_fetch_ensembl_seq(chrom, upstream_ee - 3, upstream_ee + 20))
            if upstream_ee is not None else ""
        )

    return SpliceWindows(
        donor_seq=donor_seq,
        acceptor_seq=acceptor_seq,
        ppt_seq=ppt_seq,
        upstream_donor_seq=upstream_donor_seq,
        downstream_acceptor_seq=downstream_acceptor_seq,
        source="ensembl",
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
