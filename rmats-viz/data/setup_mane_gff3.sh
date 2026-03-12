#!/bin/bash
# =============================================================================
# setup_mane_gff3.sh
# Download the MANE Select GFF3 file from NCBI for local MANE transcript
# annotation (no Ensembl REST API dependency).
#
# This file provides:
#   - Gene → MANE Select transcript mapping
#   - Exon coordinates for transcript diagrams
#   - CDS coordinates for frame class computation
#
# Usage:
#   bash setup_mane_gff3.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/MANE.GRCh38.ensembl_genomic.gff.gz"

# NCBI FTP URL for the current MANE release (Ensembl-style coordinates)
MANE_URL="https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.4.ensembl_genomic.gff.gz"
# Fallback: try v1.3 if v1.4 is not available
MANE_URL_FALLBACK="https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.3.ensembl_genomic.gff.gz"

if [ -f "$OUT" ]; then
  echo "MANE GFF3 already exists: $OUT"
  echo "  MANE_GFF3=$OUT"
  exit 0
fi

echo "[1/2] Downloading MANE Select GFF3 (~3 MB)..."

download_ok=false
for url in "$MANE_URL" "$MANE_URL_FALLBACK"; do
  echo "  Trying: $url"
  if command -v curl > /dev/null 2>&1; then
    if curl -fSL --retry 3 -o "$OUT" "$url" 2>/dev/null; then
      download_ok=true
      break
    fi
  elif command -v wget > /dev/null 2>&1; then
    if wget -q -O "$OUT" "$url" 2>/dev/null; then
      download_ok=true
      break
    fi
  else
    echo "ERROR: neither curl nor wget found." >&2
    exit 1
  fi
done

if [ "$download_ok" = false ]; then
  # Try listing current directory to find the latest version
  echo "  Specific versions not found, trying to discover latest..."
  if command -v curl > /dev/null 2>&1; then
    latest=$(curl -fsSL "https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/" 2>/dev/null \
      | grep -oP 'MANE\.GRCh38\.v[\d.]+\.ensembl_genomic\.gff\.gz' | sort -V | tail -1)
    if [ -n "$latest" ]; then
      echo "  Found: $latest"
      curl -fSL --retry 3 -o "$OUT" "https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/$latest" && download_ok=true
    fi
  fi
fi

if [ "$download_ok" = false ]; then
  rm -f "$OUT"
  echo "ERROR: Failed to download MANE GFF3. The app will fall back to Ensembl REST API." >&2
  echo "You can manually download from:" >&2
  echo "  https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/" >&2
  echo "Place the file at: $OUT" >&2
  exit 1
fi

echo "[2/2] Verifying file..."
if gzip -t "$OUT" 2>/dev/null; then
  echo "OK — MANE GFF3 is valid."
else
  echo "WARNING: File may be corrupted. Delete and re-download if needed."
fi

# Count genes
n_genes=$(zcat "$OUT" 2>/dev/null | grep -c $'\ttranscript\t' || echo "?")
echo ""
echo "MANE GFF3: $OUT"
echo "Transcripts: $n_genes"
echo ""
echo "Set env var:"
echo "  MANE_GFF3=$OUT"
