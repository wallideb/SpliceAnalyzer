"""
Annotations router
==================
Aggregates external gene annotation data from multiple sources:

    PanelApp Australia – disease panel confidence ratings
    Gene Ontology      – GO terms via mygene.info
    UniProt            – reviewed protein function description
    STRING-DB          – protein–protein interaction evidence + PMIDs

Endpoints
---------
GET /api/v1/annotations/gene/{symbol}
    Full annotation for a gene by HUGO symbol.
    Optional query param ``ensembl_id`` improves GO term lookup precision.

GET /api/v1/annotations/interactions
    STRING-DB interaction between two genes (gene_a, gene_b).
    Also returns PMIDs from Europe PMC when text-mining evidence is present.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query

from app.schemas.annotation import GeneAnnotation, GOTerm, PanelEntry, ProteinFunction
from app.services.gene_ontology import get_go_terms
from app.services.panelapp import get_panels_for_gene
from app.services.uniprot import get_protein_function

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.get(
    "/gene/{symbol}",
    response_model=GeneAnnotation,
    summary="Gene annotation (PanelApp + GO + UniProt)",
)
async def gene_annotation(
    symbol: str,
    ensembl_id: str | None = Query(None, description="Ensembl stable gene ID for precise GO lookup"),
) -> GeneAnnotation:
    """
    Fetch combined annotations for a gene in parallel:

    - **PanelApp Australia**: disease panels (green / amber / red confidence)
    - **Gene Ontology**: BP, MF, CC terms via mygene.info
    - **UniProt**: reviewed protein function summary

    If an external service is unavailable the corresponding field is
    returned empty/null rather than raising an error.
    """
    symbol = symbol.upper()

    panels_raw, go_raw, protein_raw = await asyncio.gather(
        get_panels_for_gene(symbol),
        get_go_terms(symbol, ensembl_id),
        get_protein_function(symbol),
        return_exceptions=True,
    )

    # Safely handle unexpected exceptions from gather
    panels: list[PanelEntry] = []
    if isinstance(panels_raw, list):
        panels = [PanelEntry(**p) for p in panels_raw]
    else:
        logger.warning("PanelApp gather error for %r: %s", symbol, panels_raw)

    go_terms: list[GOTerm] = []
    if isinstance(go_raw, list):
        go_terms = [GOTerm(**t) for t in go_raw]
    else:
        logger.warning("GO gather error for %r: %s", symbol, go_raw)

    protein_function: ProteinFunction | None = None
    if isinstance(protein_raw, dict):
        protein_function = ProteinFunction(**protein_raw)
    elif not isinstance(protein_raw, Exception) and protein_raw is not None:
        pass  # unexpected type – skip
    elif isinstance(protein_raw, Exception):
        logger.warning("UniProt gather error for %r: %s", symbol, protein_raw)

    return GeneAnnotation(
        symbol=symbol,
        ensembl_id=ensembl_id,
        panels=panels,
        go_terms=go_terms,
        protein_function=protein_function,
    )


@router.get(
    "/interactions",
    response_model=dict,
    summary="STRING-DB interaction between two genes",
)
async def gene_interactions(
    gene_a: str = Query(..., description="First gene HUGO symbol (e.g. BRCA1)"),
    gene_b: str = Query(..., description="Second gene HUGO symbol (e.g. TP53)"),
    species: int = Query(9606, description="NCBI taxonomy ID (9606 = Homo sapiens)"),
) -> dict:
    """
    Retrieve STRING-DB interaction data between two genes.

    Returns channel-level evidence scores (neighbourhood, fusion,
    co-occurrence, co-expression, experimental, database, text-mining).
    When text-mining evidence (tscore > 0) is present, co-mentioning
    PMIDs are also fetched from Europe PMC.
    """
    from app.services.stringdb import get_interaction  # local import avoids circular deps

    return await get_interaction(gene_a, gene_b, species)
