"""
Gene Ontology service
=====================
Retrieves GO terms for a gene using the mygene.info API (already used
for gene autocomplete).  Returns terms from the three GO aspects:

    BP – Biological Process
    MF – Molecular Function
    CC – Cellular Component

External endpoint:
    GET https://mygene.info/v3/query?q=ensembl.gene:{ensg_id}&fields=go,symbol
    or by symbol if no ENSG ID is available:
    GET https://mygene.info/v3/query?q=symbol:{symbol}&fields=go,symbol&species=human
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_MYGENE_BASE = "https://mygene.info/v3"
_TIMEOUT = 8.0

# Maximum GO terms per aspect to return (avoid flooding the UI)
_MAX_PER_ASPECT = 8


def _extract_go_terms(go_raw: dict | list | None) -> list[dict]:
    """
    Parse the ``go`` field from a mygene.info hit.

    mygene.info returns GO data under ``hit.go`` as a dict of aspects:
        {"BP": [...], "MF": [...], "CC": [...]}
    Each list element may be a dict (single entry) or the aspect value
    may itself be a single dict when there is only one term.
    """
    if not go_raw or not isinstance(go_raw, dict):
        return []

    results: list[dict] = []
    for aspect in ("BP", "MF", "CC"):
        terms = go_raw.get(aspect, [])
        if isinstance(terms, dict):
            terms = [terms]
        for term in terms[:_MAX_PER_ASPECT]:
            go_id = term.get("id", "")
            label = term.get("term", "")
            evidence = term.get("evidence", "")
            if go_id and label:
                results.append(
                    {
                        "id": go_id,
                        "term": label,
                        "category": aspect,
                        "evidence": evidence,
                    }
                )
    return results


async def get_go_terms(
    symbol: str,
    ensembl_id: str | None = None,
) -> list[dict]:
    """
    Fetch GO terms for a gene from mygene.info.

    Queries by Ensembl ID first (more precise), falls back to symbol.

    Args:
        symbol:     HUGO gene symbol, e.g. "BRCA1".
        ensembl_id: Ensembl stable gene ID (optional), e.g. "ENSG00000012048".

    Returns:
        List of dicts: [{"id", "term", "category", "evidence"}, ...]
    """
    query = f"ensembl.gene:{ensembl_id}" if ensembl_id else f"symbol:{symbol}"
    params = {
        "q": query,
        "fields": "go,symbol",
        "species": "human",
        "size": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_MYGENE_BASE}/query", params=params)
            resp.raise_for_status()
            data = resp.json()

        hits = data.get("hits", [])
        if not hits:
            return []

        return _extract_go_terms(hits[0].get("go"))

    except httpx.HTTPError as exc:
        logger.warning("mygene.info GO lookup failed for %r: %s", symbol, exc)
        return []
