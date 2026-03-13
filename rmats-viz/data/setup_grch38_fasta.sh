#!/bin/bash
# =============================================================================
# setup_genome_fasta.sh
# Download the full GRCh38 genome FASTA (UCSC IDs, no ALT contigs) and index
# with samtools.
#
# If the FASTA already exists but the .fai index is missing, only indexing runs.
#
# Usage:
#   bash setup_grch38_fasta.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/GRCh38.fa"
GZ="$SCRIPT_DIR/GRCh38.fna.gz"

GENOME_URL="https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz"

# Skip everything if both FASTA and index already exist
if [ -f "$OUT" ] && [ -f "${OUT}.fai" ]; then
  echo "GRCh38.fa and index already exist — skipping."
  echo "  GRCH38_FASTA=$OUT"
  exit 0
fi

# Download only if the FASTA itself is missing
if [ ! -f "$OUT" ]; then
  echo "[1/3] Downloading full GRCh38 genome FASTA (~800 MB compressed)..."
  if command -v curl > /dev/null 2>&1; then
    curl -fSL --retry 3 -o "$GZ" "$GENOME_URL"
  elif command -v wget > /dev/null 2>&1; then
    wget -q --show-progress -O "$GZ" "$GENOME_URL"
  else
    echo "ERROR: neither curl nor wget found. Install one and retry." >&2
    exit 1
  fi

  echo "[2/3] Decompressing..."
  gunzip -c "$GZ" > "$OUT"
  rm -f "$GZ"
else
  echo "FASTA exists but index is missing — indexing only."
fi

echo "[2/3] Indexing with samtools faidx..."
samtools faidx "$OUT"

echo "[3/3] Done."
echo "FASTA  : $OUT"
echo "Index  : ${OUT}.fai"
echo ""
echo "Contigs:"
cut -f1 "${OUT}.fai" | head -5
echo "..."
echo ""
echo "Set env var:"
echo "  GRCH38_FASTA=$OUT"
