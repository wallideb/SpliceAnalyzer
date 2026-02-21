"""
Annotations router
==================
Aggregates external gene annotation data from multiple sources:

    PanelApp Australia – disease panel confidence ratings
    Gene Ontology      – GO terms via mygene.info
    UniProt            – reviewed protein function description

All three sources are queried in parallel (asyncio.gather) to minimise
latency.

Endpoints
---------
GET /api/v1/annotations/gene/{symbol}
    Full annotation for a gene by HUGO symbol.
    Optional query param ``ensembl_id`` improves GO term lookup precision.
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
