#!/usr/bin/env bash
# =============================================================================
# setup_chr19_fasta.sh
# Concatenate the 3 chr19 FASTA parts, produce GRCh38.fa (chr19 only for dev),
# then index with samtools faidx.
#
# Usage (from /home/user/Test_1/data/):
#   bash setup_chr19_fasta.sh
#
# For production: replace GRCh38.fa with the full genome FASTA.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/GRCh38.fa"

echo "[1/3] Concatenating chr19 FASTA parts..."
cat \
  "$SCRIPT_DIR/chr19GRCh38_part1.fasta" \
  "$SCRIPT_DIR/chr19GRCh38_part2.fasta" \
  "$SCRIPT_DIR/chr19GRCh38_part3.fasta" \
  > "$OUT"

echo "[2/3] Indexing with samtools faidx..."
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
