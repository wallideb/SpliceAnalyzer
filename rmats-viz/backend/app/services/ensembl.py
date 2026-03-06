"""
Ensembl API service
===================
Provides gene search and lookup backed by two external APIs:

1. **mygene.info** (primary, autocomplete)
   - Endpoint: https://mygene.info/v3/query
   - Supports wildcard prefix queries (``symbol:BRCA*``)
   - Returns gene symbol + Ensembl stable ID in one call
   - Free, open, no authentication required

2. **Ensembl REST API** (fallback, exact lookup)
   - Endpoint: https://rest.ensembl.org/lookup/symbol/{species}/{symbol}
   - Used when mygene.info returns no results
   - Authoritative source for ENSG IDs

Public functions
----------------
- search_genes(query, species, limit)  → list[dict]
      Prefix autocomplete via mygene.info wildcard query.
- lookup_gene(symbol, species)         → dict | None
      Exact lookup via Ensembl REST API.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MYGENE_BASE = "https://mygene.info/v3"
_ENSEMBL_REST_BASE = "https://rest.ensembl.org"
_REQUEST_TIMEOUT = 8.0  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_gene_entry(symbol: str, ensembl_id: str) -> dict[str, str]:
    """Return a normalised gene entry dict used throughout the app."""
    symbol = symbol.upper()
    return {
        "symbol": symbol,
        "ensembl_id": ensembl_id,
        "display": f"{symbol} ({ensembl_id})",
    }


def _species_name(species: str) -> str:
    """Map internal species identifier to mygene.info species name."""
    _map = {
        "homo_sapiens": "human",
        "mus_musculus": "mouse",
    }
    return _map.get(species.lower(), "human")


async def _mygene_search(query: str, species: str, limit: int) -> list[dict[str, str]]:
    """
    Query mygene.info for genes matching a partial symbol (wildcard prefix).

    Uses ``symbol:{query}*`` so "BRCA" returns "BRCA1", "BRCA2", etc.
    The ``ensembl.gene`` field provides the ENSG stable ID directly.

    Response structure (simplified):
        {
          "hits": [
            {
              "symbol": "BRCA1",
              "ensembl": {"gene": "ENSG00000012048"}   ← str or list
            },
            ...
          ]
        }
    """
    params = {
        "q": f"symbol:{query}*",
        "species": _species_name(species),
        "fields": "symbol,ensembl.gene",
        "size": limit,
        "sort": "_score",
    }
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.get(f"{_MYGENE_BASE}/query", params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for hit in data.get("hits", []):
        symbol = hit.get("symbol", "")
        ensembl_raw = hit.get("ensembl", {})

        # ``ensembl.gene`` can be a plain string or a list when a gene has
        # multiple Ensembl records – always pick the first.
        if isinstance(ensembl_raw, list):
            ensembl_raw = ensembl_raw[0] if ensembl_raw else {}

        ensg_id = ""
        if isinstance(ensembl_raw, dict):
            gene_val = ensembl_raw.get("gene", "")
            # gene_val itself can be a list too
            if isinstance(gene_val, list):
                gene_val = gene_val[0] if gene_val else ""
            ensg_id = gene_val

        if symbol and ensg_id and ensg_id.startswith("ENSG") and ensg_id not in seen:
            seen.add(ensg_id)
            results.append(_make_gene_entry(symbol, ensg_id))

    return results


async def _ensembl_lookup(symbol: str, species: str) -> dict[str, str] | None:
    """
    Exact gene lookup via the Ensembl REST API.

    Returns a gene entry dict if the symbol is found, otherwise ``None``.

    Response structure (simplified):
        {"id": "ENSG00000012048", "display_name": "BRCA1", "object_type": "Gene", ...}
    """
    url = f"{_ENSEMBL_REST_BASE}/lookup/symbol/{species}/{symbol}"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(
                url,
                headers={"Accept": "application/json"},
            )
            if resp.status_code in (400, 404):
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search_genes(
    query: str,
    species: str = "homo_sapiens",
    limit: int = 10,
) -> list[dict[str, str]]:
    """
    Search for genes by partial symbol (autocomplete).

    Primary source: mygene.info wildcard query (``symbol:BRCA*``).
    Fallback:       Ensembl REST exact lookup if mygene.info returns nothing.

    Args:
        query:   Partial or full HUGO gene symbol, e.g. "BRCA" or "TP53".
        species: Species identifier, default "homo_sapiens".
        limit:   Maximum results to return, default 10.

    Returns:
        List of dicts: [{"symbol": "BRCA1", "ensembl_id": "ENSG…", "display": "BRCA1 (ENSG…)"}]
    """
    if not query or len(query.strip()) < 2:
        return []

    query = query.strip().upper()

    try:
        results = await _mygene_search(query, species, limit)
        if results:
            return results
    except Exception as exc:
        logger.warning(
            "mygene.info search failed for %r: %s – falling back to Ensembl REST", query, exc
        )

    # Fallback: exact Ensembl REST lookup
    gene = await _ensembl_lookup(query, species)
    return [gene] if gene else []


async def lookup_gene(
    symbol: str,
    species: str = "homo_sapiens",
) -> dict[str, str] | None:
    """
    Resolve an exact HUGO gene symbol to its Ensembl stable ID.

    Args:
        symbol:  Exact HUGO gene symbol, e.g. "BRCA1".
        species: Species identifier, default "homo_sapiens".

    Returns:
        Gene entry dict or ``None`` if not found.
    """
    return await _ensembl_lookup(symbol, species)
