"""
Local MANE GFF3 parser
======================
Provides MANE Select transcript annotation from a **local GFF3 file**,
eliminating the dependency on the Ensembl REST API for MANE lookups.

The GFF3 file can be downloaded from NCBI:
  https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/

Expected file: ``MANE.GRCh38.v*.ensembl_genomic.gff.gz``

The file is parsed once on first access and cached in memory as a dict
keyed by Ensembl gene ID.  Typical memory usage is ~30 MB for ~19k genes.
"""

from __future__ import annotations

import gzip
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory index (populated lazily on first call)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_loaded = False

# gene_id → { transcript_id, exons: [{start, end}], cds: [{start, end}], strand }
_gene_index: dict[str, dict[str, Any]] = {}

# transcript_id → same dict (secondary lookup)
_tx_index: dict[str, dict[str, Any]] = {}


def _parse_attributes(attr_str: str) -> dict[str, str]:
    """Parse GFF3 column-9 attributes into a dict."""
    result: dict[str, str] = {}
    for pair in attr_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        key, _, val = pair.partition("=")
        result[key] = val
    return result


def load_mane_gff3(path: str | Path) -> bool:
    """Load and index a MANE GFF3 file.  Returns True on success.

    Thread-safe: only the first caller does the actual parsing; subsequent
    calls return immediately.
    """
    global _loaded
    if _loaded:
        return True

    with _lock:
        if _loaded:
            return True

        p = Path(path)
        if not p.exists():
            logger.warning("MANE GFF3 file not found: %s", path)
            return False

        try:
            _do_parse(p)
            _loaded = True
            logger.info(
                "Loaded MANE GFF3: %d genes, %d transcripts",
                len(_gene_index),
                len(_tx_index),
            )
            return True
        except Exception as exc:
            logger.error("Failed to parse MANE GFF3 %s: %s", path, exc)
            return False


def _do_parse(path: Path) -> None:
    """Parse the GFF3 into _gene_index and _tx_index."""

    # Temporary structures while parsing
    # transcript_id → {gene_id, chr, strand, exons: [], cds: []}
    transcripts: dict[str, dict[str, Any]] = {}
    # Map from GFF ID attribute to transcript_id (for Parent resolution)
    id_to_tx: dict[str, str] = {}

    opener = gzip.open if path.suffix == ".gz" else open

    with opener(path, "rt") as fh:  # type: ignore[call-overload]
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue

            chrom, source, ftype, start_s, end_s, _, strand, _, attrs_str = parts[:9]
            attrs = _parse_attributes(attrs_str)

            # Normalise chromosome name (GFF3 uses bare numbers or "chr" prefix)
            if not chrom.startswith("chr"):
                chrom = f"chr{chrom}"

            start = int(start_s) - 1  # GFF3 is 1-based → convert to 0-based
            end = int(end_s)           # end is already correct (half-open)

            if ftype in ("mRNA", "transcript"):
                # MANE GFF3 uses Ensembl transcript IDs, sometimes versioned
                tx_id_raw = attrs.get("transcript_id") or attrs.get("ID", "")
                # Also check Name field which often has ENST...
                if not tx_id_raw.startswith("ENST"):
                    tx_id_raw = attrs.get("Name", tx_id_raw)
                # Strip version suffix for matching
                tx_id = tx_id_raw.split(".")[0] if tx_id_raw else ""

                gene_id_raw = attrs.get("gene_id", "")
                if not gene_id_raw.startswith("ENSG"):
                    # Try Parent attribute
                    gene_id_raw = attrs.get("Parent", "")
                if not gene_id_raw.startswith("ENSG"):
                    # Try extracting from ID
                    gff_id = attrs.get("ID", "")
                    # Some GFF3 files embed gene_id in attributes
                    gene_id_raw = attrs.get("gene_id", gff_id)
                gene_id = gene_id_raw.split(".")[0] if gene_id_raw else ""

                if tx_id and gene_id:
                    gff_id = attrs.get("ID", tx_id_raw)
                    transcripts[tx_id] = {
                        "transcript_id": tx_id,
                        "gene_id": gene_id,
                        "chr": chrom,
                        "strand": strand,
                        "exons": [],
                        "cds": [],
                    }
                    id_to_tx[gff_id] = tx_id

            elif ftype == "exon":
                parent = attrs.get("Parent", "")
                # Resolve parent to transcript_id
                tx_id = id_to_tx.get(parent, parent.split(".")[0])
                if tx_id in transcripts:
                    transcripts[tx_id]["exons"].append({"start": start, "end": end})

            elif ftype == "CDS":
                parent = attrs.get("Parent", "")
                tx_id = id_to_tx.get(parent, parent.split(".")[0])
                if tx_id in transcripts:
                    transcripts[tx_id]["cds"].append({"start": start, "end": end})

    # Build indices
    for tx_id, data in transcripts.items():
        # Sort exons and CDS by position
        data["exons"].sort(key=lambda e: e["start"])
        data["cds"].sort(key=lambda e: e["start"])

        gene_id = data["gene_id"]
        _tx_index[tx_id] = data

        # One gene may have multiple transcripts in the GFF3
        # (MANE Select + MANE Plus Clinical).  Prefer MANE Select.
        # In the Ensembl GFF3, the first transcript per gene is usually MANE Select.
        if gene_id not in _gene_index:
            _gene_index[gene_id] = data


def is_loaded() -> bool:
    """Return True if the MANE GFF3 index is available."""
    return _loaded


def get_mane_for_gene(gene_id: str) -> dict[str, Any] | None:
    """Look up MANE transcript data by Ensembl gene ID.

    Returns a dict with keys:
      transcript_id, gene_id, chr, strand, exons, cds
    or None if the gene is not in the MANE index.
    """
    # Strip version suffix if present
    gene_id_clean = gene_id.split(".")[0]
    return _gene_index.get(gene_id_clean)


def get_transcript_data(transcript_id: str) -> dict[str, Any] | None:
    """Look up MANE transcript data by Ensembl transcript ID."""
    tx_clean = transcript_id.split(".")[0]
    return _tx_index.get(tx_clean)


def annotate_from_local(
    gene_id: str,
    exon_start: int,
    exon_end: int,
) -> dict | None:
    """Compute MANE annotation from local GFF3 data.

    Returns a dict compatible with the Ensembl-based annotate_mane():
      transcript_id, exon_rank, frame_region, frame_class, cds_exon_length
    or None if the gene is not in the local index.
    """
    data = get_mane_for_gene(gene_id)
    if data is None:
        return None

    result: dict[str, Any] = {
        "transcript_id": data["transcript_id"],
        "exon_rank": None,
        "frame_region": "unknown",
        "frame_class": "unknown",
        "cds_exon_length": None,
    }

    exons = data["exons"]
    cds_list = data["cds"]

    # --- Exon rank by maximum overlap ---
    best_rank: int | None = None
    best_overlap = 0
    for idx, ex in enumerate(exons, start=1):
        overlap = max(0, min(exon_end, ex["end"]) - max(exon_start, ex["start"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best_rank = idx
    if best_rank is not None and best_overlap > 0:
        result["exon_rank"] = best_rank

    # --- Frame class ---
    if not cds_list:
        result["frame_region"] = "non_coding"
        result["frame_class"] = "non_coding"
        return result

    cds_start = min(c["start"] for c in cds_list)
    cds_end = max(c["end"] for c in cds_list)

    overlap_start = max(exon_start, cds_start)
    overlap_end = min(exon_end, cds_end)

    if overlap_start >= overlap_end:
        # No CDS overlap
        strand = data.get("strand", "+")
        strand_val = 1 if strand == "+" else -1
        if exon_end <= cds_start:
            result["frame_region"] = "UTR5" if strand_val == 1 else "UTR3"
        else:
            result["frame_region"] = "UTR3" if strand_val == 1 else "UTR5"
        result["frame_class"] = "non_coding"
        return result

    cod_len = overlap_end - overlap_start

    if overlap_start > exon_start or overlap_end < exon_end:
        result["frame_region"] = "partial"
    else:
        result["frame_region"] = "CDS"

    result["cds_exon_length"] = cod_len
    result["frame_class"] = "in_frame" if cod_len % 3 == 0 else "frameshift"
    return result


def get_transcript_exons_local(transcript_id: str) -> list[dict]:
    """Return exon list for a transcript from local GFF3 data.

    Returns list of {start, end, size} dicts (0-based half-open), sorted
    by position.  Returns empty list if transcript not found.
    """
    data = get_transcript_data(transcript_id)
    if data is None:
        return []
    return [
        {"start": e["start"], "end": e["end"], "size": e["end"] - e["start"]}
        for e in data["exons"]
    ]
