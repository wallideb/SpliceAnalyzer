"""
Genes router
============
Provides gene search and lookup endpoints backed by the Ensembl API.

Endpoints
---------
GET /api/v1/genes/search
    Autocomplete-friendly gene search.  Accepts a partial gene symbol and
    returns up to ``limit`` matching genes with their ENSG IDs.

GET /api/v1/genes/lookup/{symbol}
    Exact gene lookup by HUGO symbol.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.gene import GeneEntry, GeneSearchResponse
from app.services.ensembl import lookup_gene, search_genes

router = APIRouter(prefix="/genes", tags=["genes"])


@router.get("/search", response_model=GeneSearchResponse, summary="Autocomplete gene search")
async def gene_search(
    q: str = Query(..., min_length=2, description="Partial or full gene symbol (HUGO nomenclature)"),
    species: str = Query("homo_sapiens", description="Species identifier"),
    limit: int = Query(10, ge=1, le=25, description="Maximum number of results"),
) -> GeneSearchResponse:
    """
    Search genes by partial symbol using the EBI Search / Ensembl APIs.

    Suitable for live autocomplete: send the user's partial input (≥ 2 chars)
    and receive a ranked list of matching genes with their Ensembl stable IDs.

    Example response:
    ```json
    {
      "query": "BRCA",
      "results": [
        {"symbol": "BRCA1", "ensembl_id": "ENSG00000012048", "display": "BRCA1 (ENSG00000012048)"},
        {"symbol": "BRCA2", "ensembl_id": "ENSG00000139618", "display": "BRCA2 (ENSG00000139618)"}
      ],
      "total": 2
    }
    ```
    """
    genes = await search_genes(query=q, species=species, limit=limit)
    entries = [GeneEntry(**g) for g in genes]
    return GeneSearchResponse(query=q, results=entries, total=len(entries))


@router.get("/lookup/{symbol}", response_model=GeneEntry, summary="Exact gene lookup")
async def gene_lookup(
    symbol: str,
    species: str = Query("homo_sapiens", description="Species identifier"),
) -> GeneEntry:
    """
    Resolve an exact HUGO gene symbol to its Ensembl stable ID.

    Returns 404 if the symbol is not found in Ensembl.
    """
    gene = await lookup_gene(symbol=symbol, species=species)
    if gene is None:
        raise HTTPException(status_code=404, detail=f"Gene '{symbol}' not found in Ensembl ({species})")
    return GeneEntry(**gene)
