"""
Column mappings for rMATS TSV ingestion.
Handles column name variants produced by different rMATS versions.
"""

# rMATS sometimes uses 'exonStart_0base' (0-based) or 'exonStart'
# We normalise everything to the _0base name during parsing.

# Mapping from rMATS raw column name → normalised internal name
# Handles variants across rMATS versions
RAW_COL_MAP: dict[str, str] = {
    # Standard SE/RI columns
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
    # MXE first exon (recent rMATS versions) → generic exon columns
    "1stExonStart_0base": "exon_start",
    "1stExonStart": "exon_start",
    "1stExonEnd": "exon_end",
    # MXE second exon
    "2ndExonStart_0base": "second_exon_start",
    "2ndExonStart": "second_exon_start",
    "2ndExonEnd": "second_exon_end",
    # A3SS / A5SS alternative-site coordinates
    "longExonStart_0base": "long_exon_start",
    "longExonStart": "long_exon_start",
    "longExonEnd": "long_exon_end",
    "shortES": "short_es",
    "shortEE": "short_ee",
    "flankingES": "flanking_es",
    "flankingEE": "flanking_ee",
    # Counts
    "IJC_SAMPLE_1": "ijc_sample_1",
    "SJC_SAMPLE_1": "sjc_sample_1",
    "IJC_SAMPLE_2": "ijc_sample_2",
    "SJC_SAMPLE_2": "sjc_sample_2",
    # Isoform lengths (needed to interpret JCEC counts)
    "IncFormLen": "inc_form_len",
    "SkipFormLen": "skip_form_len",
    # Stats
    "PValue": "p_value",
    "FDR": "fdr",
    "IncLevel1": "inc_level_1",
    "IncLevel2": "inc_level_2",
    "IncLevelDifference": "inc_level_difference",
    # RI-specific coordinates (same as exon_start/end in RI output)
    "riExonStart_0base": "exon_start",
    "riExonStart": "exon_start",
    "riExonEnd": "exon_end",
}

# Generic coordinate columns shared by SE / RI / MXE
_GENERIC_COORD_COLS: frozenset[str] = frozenset(
    {"exon_start", "exon_end", "upstream_es", "upstream_ee", "downstream_es", "downstream_ee"}
)

# A3SS / A5SS alternative-site coordinate columns
ALT_SITE_COORD_COLS: frozenset[str] = frozenset(
    {"long_exon_start", "long_exon_end", "short_es", "short_ee", "flanking_es", "flanking_ee"}
)

# Coordinate columns that must not be *all* null for a row to be kept,
# per rMATS event type.
REQUIRED_COLS_BY_TYPE: dict[str, frozenset[str]] = {
    "SE": _GENERIC_COORD_COLS,
    "RI": _GENERIC_COORD_COLS,
    "MXE": _GENERIC_COORD_COLS | {"second_exon_start", "second_exon_end"},
    "A3SS": ALT_SITE_COORD_COLS,
    "A5SS": ALT_SITE_COORD_COLS,
}

# Backward-compatible alias (SE set)
REQUIRED_COLS: set[str] = set(REQUIRED_COLS_BY_TYPE["SE"])
