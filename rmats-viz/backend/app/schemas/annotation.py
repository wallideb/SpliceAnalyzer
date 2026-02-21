"""
Annotation schemas
==================
Pydantic models for the gene annotation endpoint that aggregates data
from PanelApp Australia, Gene Ontology (mygene.info), and UniProt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# PanelApp
# ---------------------------------------------------------------------------

class PanelEntry(BaseModel):
    """A single PanelApp panel entry for a gene."""

    panel_name: str = Field(..., description="Human-readable panel title")
    confidence_level: int = Field(..., description="1=red, 2=amber, 3=green")
    confidence_label: str = Field(..., description="'red', 'amber', or 'green'")
    disorders: list[str] = Field(default_factory=list, description="Relevant disorder names")


# ---------------------------------------------------------------------------
# Gene Ontology
# ---------------------------------------------------------------------------

class GOTerm(BaseModel):
    """A single Gene Ontology term."""

    id: str = Field(..., description="GO identifier, e.g. 'GO:0000077'")
    term: str = Field(..., description="GO term label")
    category: str = Field(..., description="'BP' (biological process), 'MF' (molecular function), or 'CC' (cellular component)")
    evidence: str = Field(default="", description="Evidence code, e.g. 'IDA', 'IEA'")


# ---------------------------------------------------------------------------
# UniProt
# ---------------------------------------------------------------------------

class ProteinFunction(BaseModel):
    """UniProt reviewed protein function annotation."""

    accession: str
    protein_name: str
    function: str
    uniprot_url: str


# ---------------------------------------------------------------------------
# Combined annotation response
# ---------------------------------------------------------------------------

class GeneAnnotation(BaseModel):
    """
    Combined annotation for a single gene, aggregating PanelApp,
    Gene Ontology, and UniProt data.
    """

    symbol: str
    ensembl_id: str | None = None

    # PanelApp Australia panels (sorted green → amber → red)
    panels: list[PanelEntry] = Field(default_factory=list)

    # GO terms (BP / MF / CC)
    go_terms: list[GOTerm] = Field(default_factory=list)

    # UniProt protein function (None if no reviewed entry found)
    protein_function: ProteinFunction | None = None
