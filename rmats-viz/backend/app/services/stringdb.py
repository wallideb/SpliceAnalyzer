"""
STRING-DB service
=================
Queries the STRING protein interaction database for evidence of
functional interaction between two genes, and retrieves PubMed IDs
(PMIDs) of co-mentioning papers via Europe PMC when text-mining
evidence is present.

External endpoints used
-----------------------
STRING REST API:
    GET https://string-db.org/api/json/network
        Returns interaction scores across all evidence channels.
        Empty list → no interaction found.

Europe PMC REST API (only queried when tscore > 0):
    GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
        Searches for abstracts co-mentioning both gene symbols.

Evidence channels returned by STRING
-------------------------------------
nscore  Neighbourhood    (conserved gene order across genomes)
fscore  Gene fusion      (genes fused as single ORF in another species)
pscore  Phylogenetic co-occurrence
ascore  Co-expression    (correlated expression patterns)
escore  Experimental     (direct protein interaction experiments)
dscore  Database         (curated pathway/complex databases)
tscore  Text mining      (Medline abstract co-mentions)
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_STRING_BASE = "https://string-db.org/api/json"
_EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_TIMEOUT = 10.0

# Channel metadata: key, human label, hex colour (STRING visual convention)
CHANNEL_META: list[dict] = [
    {"key": "nscore", "label": "Genomic neighbourhood",  "color": "#2CA02C"},  # green
    {"key": "fscore", "label": "Gene fusion",            "color": "#D62728"},  # red
    {"key": "pscore", "label": "Phylogenetic co-occurrence", "color": "#1F77B4"},  # blue
    {"key": "ascore", "label": "Co-expression",          "color": "#333333"},  # dark
    {"key": "escore", "label": "Experimental",           "color": "#E377C2"},  # pink
    {"key": "dscore", "label": "Curated database",       "color": "#17BECF"},  # cyan
    {"key": "tscore", "label": "Text mining",            "color": "#FFC000"}, # amber
]


async def _query_string(gene_a: str, gene_b: str, species: int) -> dict | None:
    """
    Call the STRING /network endpoint for a pair of genes.

    Returns the raw interaction dict from STRING, or None if no
    interaction is found or the API is unreachable.
    """
    # STRING uses CR (%0D) to separate multiple identifiers
    identifiers = f"{gene_a}\r{gene_b}"
    params = {
        "identifiers": identifiers,
        "species": species,
        "caller_identity": "rmats-viz",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_STRING_BASE}/network", params=params)
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return None
        # Pick the interaction between our two genes specifically
        # (STRING may return interactions involving neighbours too)
        g_a = gene_a.upper()
        g_b = gene_b.upper()
        for item in data:
            a = item.get("preferredName_A", "").upper()
            b = item.get("preferredName_B", "").upper()
            if (a == g_a and b == g_b) or (a == g_b and b == g_a):
                return item
        # If exact match not found, return the first result
        return data[0] if data else None
    except httpx.HTTPError as exc:
        logger.warning("STRING API error for %r/%r: %s", gene_a, gene_b, exc)
        return None


async def _query_europepmc(gene_a: str, gene_b: str, limit: int = 5) -> list[dict]:
    """
    Search Europe PMC for PubMed abstracts co-mentioning both gene symbols.

    Uses the SRC:MED filter to restrict to PubMed articles so the pmid
    field is always populated.  Falls back to an unquoted query if the
    strict quoted search returns no results.

    Returns a list of dicts: [{"pmid", "title", "year", "authors"}, ...]
    """

    async def _search(query: str, client: httpx.AsyncClient) -> list[dict]:
        params = {
            "query": query,
            "format": "json",
            "pageSize": limit,
            "resultType": "lite",
            "sort": "RELEVANCE",
            "synonym": "TRUE",
        }
        resp = await client.get(f"{_EUROPEPMC_BASE}/search", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("resultList", {}).get("result", []):
            pmid = item.get("pmid") or item.get("id", "")
            if not pmid or not str(pmid).isdigit():
                continue
            results.append(
                {
                    "pmid": str(pmid),
                    "title": item.get("title", "").rstrip("."),
                    "year": item.get("pubYear", ""),
                    "authors": item.get("authorString", ""),
                }
            )
        return results

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Try strict query first (both genes quoted, PubMed source)
            strict = f'("{gene_a}" AND "{gene_b}") SRC:MED'
            results = await _search(strict, client)
            if not results:
                # Relaxed: no source filter, no quotes
                relaxed = f"{gene_a} AND {gene_b} AND SRC:MED"
                results = await _search(relaxed, client)
        return results[:limit]
    except httpx.HTTPError as exc:
        logger.warning("Europe PMC error for %r/%r: %s", gene_a, gene_b, exc)
        return []


async def get_interaction(
    gene_a: str,
    gene_b: str,
    species: int = 9606,
) -> dict:
    """
    Retrieve the STRING-DB interaction between two genes.

    Also fetches PubMed IDs from Europe PMC when text-mining evidence
    is present (tscore > 0).

    Returns a dict with the following structure:
        {
            "has_interaction": bool,
            "gene_a": str,
            "gene_b": str,
            "combined_score": float,     # 0.0 – 1.0
            "channels": {                # active channels only (score > 0)
                "escore": 0.9,
                "dscore": 0.7,
                ...
            },
            "channel_meta": [            # metadata for rendering
                {"key": "escore", "label": "...", "color": "#..."},
                ...
            ],
            "pmids": [                   # empty when tscore == 0
                {"pmid": "12345678", "title": "...", "year": "2021", "authors": "..."},
            ],
            "string_url": str,
        }
    """
    gene_a = gene_a.upper()
    gene_b = gene_b.upper()

    interaction = await _query_string(gene_a, gene_b, species)

    if not interaction:
        return {
            "has_interaction": False,
            "gene_a": gene_a,
            "gene_b": gene_b,
            "combined_score": 0.0,
            "channels": {},
            "channel_meta": [],
            "pmids": [],
            "string_url": "",
        }

    # Extract channel scores (only keep those > 0)
    channels: dict[str, float] = {}
    active_meta: list[dict] = []
    for ch in CHANNEL_META:
        score = float(interaction.get(ch["key"], 0) or 0)
        if score > 0:
            channels[ch["key"]] = round(score, 3)
            active_meta.append(ch)

    combined = float(interaction.get("score", 0) or 0)

    # Fetch PMIDs only when text-mining evidence exists
    pmids: list[dict] = []
    if channels.get("tscore", 0) > 0:
        pmids = await _query_europepmc(gene_a, gene_b)

    string_url = (
        f"https://string-db.org/cgi/network?identifiers="
        f"{gene_a}%0D{gene_b}&species={species}"
    )

    return {
        "has_interaction": True,
        "gene_a": gene_a,
        "gene_b": gene_b,
        "combined_score": round(combined, 3),
        "channels": channels,
        "channel_meta": active_meta,
        "pmids": pmids,
        "string_url": string_url,
    }
