"""
Enrichr gene-set enrichment analysis
======================================
Queries the Enrichr REST API (Ma'ayan Lab, Icahn School of Medicine)
to perform gene-set enrichment on significant splicing events.

Only gene symbols are accepted by Enrichr.  Since rMATS events carry
Ensembl gene IDs (ENSG…), the caller must provide pre-mapped symbols.

Workflow
--------
1. Collect unique gene symbols from significant events.
2. POST the gene list to Enrichr ``/addList``.
3. GET enrichment results for all libraries in parallel (ThreadPoolExecutor).

Reproducibility note
--------------------
Gene-set library contents are retrieved live from the Enrichr API at the
time of each analysis run.  Libraries are versioned by name (e.g.,
KEGG_2021_Human, GO_Biological_Process_2023), but Enrichr may update their
contents between releases without changing the name.  For publication,
record the date of the API call alongside results; consider archiving the
raw Enrichr response JSON to ensure exact reproducibility.

References
----------
- Chen EY et al. Enrichr. BMC Bioinformatics 2013; 14:128
- Kuleshov MV et al. Enrichr update 2016. NAR 2016; 44:W90-W97
- Xie Z et al. Gene set knowledge discovery with Enrichr. Curr Protoc 2021
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

ENRICHR_URL = "https://maayanlab.cloud/Enrichr"

# Libraries queried by default — curated set relevant for splicing biology
DEFAULT_LIBRARIES = [
    "KEGG_2021_Human",
    "GO_Biological_Process_2023",
    "GO_Molecular_Function_2023",
    "Reactome_2022",
    "WikiPathway_2023_Human",
]

TIMEOUT = 15  # seconds per HTTP call

# Gene-set sizes per library, fetched at most once per process from the GMT
# endpoint (``geneSetLibrary?mode=text``).  The ``/enrich`` endpoint does not
# return set sizes and the term name must not be parsed for them (GO ids,
# KEGG terms without parentheses, ...).  A failed fetch caches ``{}`` so the
# request is not retried on every enrichment run.
_LIBRARY_SIZE_CACHE: dict[str, dict[str, int]] = {}
_LIBRARY_SIZE_LOCK = threading.Lock()


def get_library_sizes(lib: str) -> dict[str, int]:
    """Return {term: number_of_genes} for an Enrichr library (cached per process).

    Parses the GMT text (``term<TAB>description<TAB>gene1<TAB>gene2...``).
    Network or parsing failures yield an empty dict (and are cached as such).
    """
    with _LIBRARY_SIZE_LOCK:
        cached = _LIBRARY_SIZE_CACHE.get(lib)
    if cached is not None:
        return cached

    sizes: dict[str, int] = {}
    try:
        resp = requests.get(
            f"{ENRICHR_URL}/geneSetLibrary",
            params={"mode": "text", "libraryName": lib},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            term = parts[0].strip()
            genes = [g for g in parts[2:] if g.strip()]
            if term:
                sizes[term] = len(genes)
        logger.info("Enrichr: cached %d gene-set sizes for %s", len(sizes), lib)
    except Exception as exc:
        logger.warning("Enrichr: could not fetch gene-set sizes for %s: %s", lib, exc)
        sizes = {}

    with _LIBRARY_SIZE_LOCK:
        _LIBRARY_SIZE_CACHE.setdefault(lib, sizes)
        return _LIBRARY_SIZE_CACHE[lib]


@dataclass
class EnrichrTerm:
    """One enriched term from a single library."""
    library: str
    rank: int
    term: str
    p_value: float
    adjusted_p_value: float
    z_score: float
    combined_score: float
    overlap: str          # e.g. "3/50"
    genes: list[str]


@dataclass
class EnrichrResult:
    """Full enrichment result for the submitted gene list."""
    n_genes_submitted: int
    terms: list[EnrichrTerm]
    error: str | None = None


def _fetch_library(user_list_id: int, lib: str, top_n: int) -> list[EnrichrTerm]:
    """Fetch enrichment for a single library. Designed to run in a thread."""
    resp = requests.get(
        f"{ENRICHR_URL}/enrich",
        params={"userListId": user_list_id, "backgroundType": lib},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    enrichment = resp.json()
    # Enrichr returns {library_name: [[rank, term, pval, zscore, combined, overlap_genes, adj_pval, ...]]}
    rows = enrichment.get(lib, [])
    set_sizes = get_library_sizes(lib) if rows else {}
    terms: list[EnrichrTerm] = []
    for i, row in enumerate(rows[:top_n]):
        # row format: [rank, term, pval, zscore, combined_score, overlap_genes, adj_pval, old_pval, old_adj_pval]
        if len(row) < 7:
            continue
        overlap_genes = row[5] if isinstance(row[5], list) else []
        term_str = str(row[1])
        # Overlap string: "k/n" when the gene-set size n is known from the
        # cached GMT, otherwise just "k" (never parsed from the term name).
        size = set_sizes.get(term_str)
        overlap_str = f"{len(overlap_genes)}/{size}" if size else f"{len(overlap_genes)}"
        terms.append(EnrichrTerm(
            library=lib,
            rank=int(row[0]) if row[0] is not None else i + 1,
            term=term_str,
            p_value=float(row[2]),
            adjusted_p_value=float(row[6]),
            z_score=float(row[3]),
            combined_score=float(row[4]),
            overlap=overlap_str,
            genes=overlap_genes,
        ))
    return terms


def run_enrichment(
    gene_symbols: list[str],
    libraries: list[str] | None = None,
    top_n: int = 10,
) -> EnrichrResult:
    """Submit a gene list to Enrichr and return top enriched terms.

    Parameters
    ----------
    gene_symbols : unique gene symbols (HGNC).
    libraries : Enrichr library names to query. Defaults to DEFAULT_LIBRARIES.
    top_n : max terms to return per library.

    Library GETs are issued in parallel (one thread per library), reducing
    wall-clock time from ~5 × TIMEOUT to ~1 × TIMEOUT.

    Returns an EnrichrResult. On error, the ``error`` field is set and
    ``terms`` is empty — the caller should handle gracefully.
    """
    if not gene_symbols:
        return EnrichrResult(
            n_genes_submitted=0,
            terms=[],
            error="No gene symbols provided",
        )

    libs = libraries or DEFAULT_LIBRARIES
    unique_symbols = sorted(set(gene_symbols))

    # Step 1: POST gene list
    try:
        payload = {
            "list": (None, "\n".join(unique_symbols)),
            "description": (None, "SpliceAnalyzer significant events"),
        }
        resp = requests.post(
            f"{ENRICHR_URL}/addList",
            files=payload,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        user_list_id = data.get("userListId", 0)
    except Exception as exc:
        logger.warning("Enrichr addList failed: %s", exc)
        return EnrichrResult(
            n_genes_submitted=len(unique_symbols),
            terms=[],
            error=f"Enrichr API error: {exc}",
        )

    # Step 2: GET enrichment for all libraries in parallel
    all_terms: list[EnrichrTerm] = []
    with ThreadPoolExecutor(max_workers=len(libs)) as pool:
        futures = {
            pool.submit(_fetch_library, user_list_id, lib, top_n): lib
            for lib in libs
        }
        for future in as_completed(futures):
            lib = futures[future]
            try:
                all_terms.extend(future.result())
            except Exception as exc:
                logger.warning("Enrichr enrich failed for %s: %s", lib, exc)

    return EnrichrResult(
        n_genes_submitted=len(unique_symbols),
        terms=all_terms,
    )
