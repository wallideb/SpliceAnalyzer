"""
UniProt service
===============
Retrieves the reviewed (Swiss-Prot) protein function description for a
human gene using the UniProt REST API.

This replaces the GeneCards source (no public API) with UniProt's
curated, freely accessible protein function annotations.

External endpoint:
    GET https://rest.uniprot.org/uniprotkb/search
        ?query=gene:{symbol} AND organism_id:9606 AND reviewed:true
        &fields=cc_function,protein_name,id
        &format=json&size=1
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_UNIPROT_BASE = "https://rest.uniprot.org/uniprotkb"
_TIMEOUT = 8.0


async def get_protein_function(symbol: str) -> dict | None:
    """
    Return the UniProt curated function description for a human gene.

    Args:
        symbol: HUGO gene symbol, e.g. "BRCA1".

    Returns:
        Dict with keys ``accession``, ``protein_name``, ``function`` (str),
        or ``None`` if not found.
    """
    params = {
        "query": f"gene_exact:{symbol.upper()} AND organism_id:9606 AND reviewed:true",
        "fields": "cc_function,protein_name,accession",
        "format": "json",
        "size": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_UNIPROT_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        entry = results[0]
        accession = entry.get("primaryAccession", "")

        # Protein name (recommended name → full name)
        protein_name = (
            entry.get("proteinDescription", {})
            .get("recommendedName", {})
            .get("fullName", {})
            .get("value", "")
        )

        # Function comment (first FUNCTION comment block)
        function_text = ""
        for comment in entry.get("comments", []):
            if comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts:
                    function_text = texts[0].get("value", "")
                    break

        if not function_text:
            return None

        return {
            "accession": accession,
            "protein_name": protein_name,
            "function": function_text,
            "uniprot_url": f"https://www.uniprot.org/uniprotkb/{accession}",
        }

    except httpx.HTTPError as exc:
        logger.warning("UniProt request failed for %r: %s", symbol, exc)
        return None
