"""
Column mappings for rMATS TSV ingestion.
Handles column name variants produced by different rMATS versions.
"""

# rMATS sometimes uses 'exonStart_0base' (0-based) or 'exonStart'
# We normalise everything to the _0base name during parsing.

# Mapping from rMATS raw column name → normalised internal name
# Handles variants across rMATS versions
RAW_COL_MAP: dict[str, str] = {
    # Standard SE/RI/A3SS/A5SS columns
    "ID": "rmats_id",
    "GeneID": "gene_id",
    "geneSymbol": "gene_symbol",
    "chr": "chr",
    "strand": "strand",
    "exonStart_0base": "exon_start",
    "exonStart": "exon_start",
    "exonEnd": "exon_end",
    "upstreamES": "upstream_es",
    "upstreamEE": "upstream_ee",
    "downstreamES": "downstream_es",
    "downstreamEE": "downstream_ee",
    # MXE second exon
    "2ndExonStart_0base": "second_exon_start",
    "2ndExonStart": "second_exon_start",
    "2ndExonEnd": "second_exon_end",
    # Counts
    "IJC_SAMPLE_1": "ijc_sample_1",
    "SJC_SAMPLE_1": "sjc_sample_1",
    "IJC_SAMPLE_2": "ijc_sample_2",
    "SJC_SAMPLE_2": "sjc_sample_2",
    # Stats
    "PValue": "p_value",
    "FDR": "fdr",
    "IncLevel1": "inc_level_1",
    "IncLevel2": "inc_level_2",
    "IncLevelDifference": "inc_level_difference",
    # RI-specific coordinates (same as exon_start/end in RI output)
    "riExonStart_0base": "exon_start",
    "riExonEnd": "exon_end",
}

# Required columns that must be present after renaming (subset)
REQUIRED_COLS = {"exon_start", "exon_end", "upstream_es", "upstream_ee", "downstream_es", "downstream_ee"}
