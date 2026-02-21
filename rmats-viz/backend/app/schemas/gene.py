"""
Gene schemas
============
Pydantic models for gene search results and stored gene entries.

``GeneEntry`` is the canonical representation used both in API responses
and in the ``mutated_genes`` JSONB column of the ``Analysis`` model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeneEntry(BaseModel):
    """A resolved gene with its Ensembl stable identifier."""

    symbol: str = Field(..., description="HUGO gene symbol, e.g. 'BRCA1'")
    ensembl_id: str = Field(..., description="Ensembl stable gene ID, e.g. 'ENSG00000012048'")
    display: str = Field(..., description="Human-readable label: 'BRCA1 (ENSG00000012048)'")

    model_config = {"from_attributes": True}


class GeneSearchResponse(BaseModel):
    """Wrapper returned by the gene search endpoint."""

    query: str
    results: list[GeneEntry]
    total: int
