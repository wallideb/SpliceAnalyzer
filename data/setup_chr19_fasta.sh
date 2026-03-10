#!/bin/bash
# =============================================================================
# setup_chr19_fasta.sh
# Download the chr19 FASTA (GRCh38.p13) from NCBI and index with samtools.
#
# Usage:
#   bash setup_chr19_fasta.sh
#
# For production: replace GRCh38.fa with the full genome FASTA.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/GRCh38.fa"
GZ="$SCRIPT_DIR/chr19.fna.gz"

NCBI_URL="https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/405/GCF_000001405.39_GRCh38.p13/GCF_000001405.39_GRCh38.p13_assembly_structure/Primary_Assembly/assembled_chromosomes/FASTA/chr19.fna.gz"

# Skip download if the final FASTA + index already exist
if [ -f "$OUT" ] && [ -f "${OUT}.fai" ]; then
  echo "GRCh38.fa and index already exist — skipping."
  echo "  GRCH38_FASTA=$OUT"
  exit 0
fi

echo "[1/3] Downloading chr19 FASTA from NCBI..."
if command -v curl > /dev/null 2>&1; then
  curl -fSL --retry 3 -o "$GZ" "$NCBI_URL"
elif command -v wget > /dev/null 2>&1; then
  wget -q --show-progress -O "$GZ" "$NCBI_URL"
else
  echo "ERROR: neither curl nor wget found. Install one and retry." >&2
  exit 1
fi

echo "[2/3] Decompressing and indexing..."
gunzip -c "$GZ" > "$OUT"
rm -f "$GZ"
samtools faidx "$OUT"

echo "[3/3] Done."
echo "FASTA  : $OUT"
echo "Index  : ${OUT}.fai"
echo ""
echo "Header line:"
grep "^>" "$OUT" | head -1
echo ""
echo "Set env var:"
echo "  GRCH38_FASTA=$OUT"
