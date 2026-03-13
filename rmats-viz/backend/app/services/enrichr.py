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
3. GET enrichment results for selected libraries.

References
----------
- Chen EY et al. Enrichr. BMC Bioinformatics 2013; 14:128
- Kuleshov MV et al. Enrichr update 2016. NAR 2016; 44:W90-W97
- Xie Z et al. Gene set knowledge discovery with Enrichr. Curr Protoc 2021
"""

from __future__ import annotations

import logging
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
    user_list_id: int
    n_genes_submitted: int
    terms: list[EnrichrTerm]
    error: str | None = None


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

    Returns an EnrichrResult. On error, the ``error`` field is set and
    ``terms`` is empty — the caller should handle gracefully.
    """
    if not gene_symbols:
        return EnrichrResult(
            user_list_id=0,
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
            user_list_id=0,
            n_genes_submitted=len(unique_symbols),
            terms=[],
            error=f"Enrichr API error: {exc}",
        )

    # Step 2: GET enrichment for each library
    all_terms: list[EnrichrTerm] = []
    for lib in libs:
        try:
            resp = requests.get(
                f"{ENRICHR_URL}/enrich",
                params={"userListId": user_list_id, "backgroundType": lib},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            enrichment = resp.json()
            # Enrichr returns {library_name: [[rank, term, pval, zscore, combined, overlap_genes, adj_pval, ...]]}
            rows = enrichment.get(lib, [])
            for i, row in enumerate(rows[:top_n]):
                # row format: [rank, term, pval, zscore, combined_score, overlap_genes, adj_pval, old_pval, old_adj_pval]
                if len(row) < 7:
                    continue
                overlap_genes = row[5] if isinstance(row[5], list) else []
                # Overlap string: "k/n" where k = overlapping genes, n = gene-set size.
                # Gene-set size is sometimes embedded in the term name (e.g. "Pathway (124)")
                # but this is library-specific and unreliable; report count only when absent.
                term_str = str(row[1])
                if "(" in term_str and term_str.endswith(")"):
                    geneset_size = term_str.rsplit("(", 1)[-1].rstrip(")")
                    overlap_str = f"{len(overlap_genes)}/{geneset_size}"
                else:
                    overlap_str = str(len(overlap_genes))
                all_terms.append(EnrichrTerm(
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
        except Exception as exc:
            logger.warning("Enrichr enrich failed for %s: %s", lib, exc)
            continue

    return EnrichrResult(
        user_list_id=user_list_id,
        n_genes_submitted=len(unique_symbols),
        terms=all_terms,
    )
