"""
Ensembl API service
===================
Provides gene search and lookup via the EBI Search REST API and the
Ensembl REST API (GRCh38).

Public functions
----------------
- search_genes(query, species, limit) -> list[GeneEntry]
    Prefix-based autocomplete using EBI Search (supports wildcard queries).
- lookup_gene(symbol, species) -> GeneEntry | None
    Exact-match lookup via the Ensembl REST API.

External endpoints used
-----------------------
- EBI Search:  https://www.ebi.ac.uk/ebisearch/ws/rest/ensembl_gene
- Ensembl REST: https://rest.ensembl.org/lookup/symbol/{species}/{symbol}
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EBI_SEARCH_BASE = "https://www.ebi.ac.uk/ebisearch/ws/rest"
_ENSEMBL_REST_BASE = "https://rest.ensembl.org"
_REQUEST_TIMEOUT = 8.0  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_gene_entry(symbol: str, ensembl_id: str) -> dict[str, str]:
    """Return a normalised gene entry dict."""
    return {
        "symbol": symbol.upper(),
        "ensembl_id": ensembl_id,
        "display": f"{symbol.upper()} ({ensembl_id})",
    }


async def _ebi_search(query: str, species: str, limit: int) -> list[dict[str, str]]:
    """
    Query the EBI Search REST API for Ensembl genes.

    The wildcard suffix ``*`` on the query enables prefix matching, making
    this suitable for live autocomplete (e.g. "BRCA" → "BRCA1", "BRCA2"…).

    Response structure (simplified):
        {
          "hitCount": 2,
          "entries": [
            {"id": "ENSG00000012048", "fields": {"name": ["BRCA1"]}},
            ...
          ]
        }
    """
    url = f"{_EBI_SEARCH_BASE}/ensembl_gene"
    params: dict[str, Any] = {
        "query": f"{query}* AND (taxonomy:{_species_taxon(species)})",
        "format": "json",
        "fields": "id,name",
        "size": limit,
    }
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict[str, str]] = []
    for entry in data.get("entries", []):
        ensg_id = entry.get("id", "")
        names = entry.get("fields", {}).get("name", [])
        symbol = names[0] if names else ensg_id
        if ensg_id.startswith("ENSG"):
            results.append(_make_gene_entry(symbol, ensg_id))
    return results


async def _ensembl_lookup(symbol: str, species: str) -> dict[str, str] | None:
    """
    Exact gene lookup via the Ensembl REST API.

    Returns a gene entry dict if the symbol is found, otherwise ``None``.

    Response structure (simplified):
        {"id": "ENSG00000012048", "display_name": "BRCA1", ...}
    """
    url = f"{_ENSEMBL_REST_BASE}/lookup/symbol/{species}/{symbol}"
    headers = {"Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 400 or resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()

        ensg_id = data.get("id", "")
        display = data.get("display_name", symbol)
        if ensg_id.startswith("ENSG"):
            return _make_gene_entry(display, ensg_id)
    except httpx.HTTPError as exc:
        logger.warning("Ensembl REST lookup failed for %r: %s", symbol, exc)
    return None


def _species_taxon(species: str) -> str:
    """Map a species name to its NCBI taxon ID for EBI Search filtering."""
    _taxon_map = {
        "homo_sapiens": "9606",
        "mus_musculus": "10090",
    }
    return _taxon_map.get(species.lower(), "9606")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search_genes(
    query: str,
    species: str = "homo_sapiens",
    limit: int = 10,
) -> list[dict[str, str]]:
    """
    Search for genes by partial symbol using EBI Search (prefix wildcard).

    Falls back to an exact Ensembl REST lookup when EBI Search returns no
    results (e.g. for very short queries or transient EBI Search issues).

    Args:
        query:   Partial or complete gene symbol (e.g. "BRCA", "TP53").
        species: Species identifier (default: "homo_sapiens").
        limit:   Maximum number of results to return (default: 10).

    Returns:
        List of gene entry dicts with keys ``symbol``, ``ensembl_id``,
        ``display`` (e.g. "BRCA1 (ENSG00000012048)").
    """
    if not query or len(query.strip()) < 2:
        return []

    query = query.strip().upper()

    try:
        results = await _ebi_search(query, species, limit)
        if results:
            return results
    except Exception as exc:
        logger.warning("EBI Search failed for %r: %s – falling back to Ensembl REST", query, exc)

    # Fallback: exact Ensembl REST lookup
    gene = await _ensembl_lookup(query, species)
    return [gene] if gene else []


async def lookup_gene(
    symbol: str,
    species: str = "homo_sapiens",
) -> dict[str, str] | None:
    """
    Exact gene lookup via the Ensembl REST API.

    Useful for resolving a known symbol to its ENSG ID when autocomplete
    is bypassed.

    Args:
        symbol:  Exact HUGO gene symbol (e.g. "BRCA1").
        species: Species identifier (default: "homo_sapiens").

    Returns:
        Gene entry dict or ``None`` if not found.
    """
    return await _ensembl_lookup(symbol, species)
