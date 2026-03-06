"""
Analysis schemas
================
Pydantic models for analysis creation, listing, and detailed responses.

``mutated_genes`` is stored as a JSONB list of :class:`GeneEntry` objects:
    [{"symbol": "BRCA1", "ensembl_id": "ENSG00000012048", "display": "BRCA1 (ENSG00000012048)"}]
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.gene import GeneEntry


class SampleGroupResponse(BaseModel):
    id: uuid.UUID
    group_label: str
    group_index: int
    sample_names: list[str]

    model_config = {"from_attributes": True}


class AnalysisCreate(BaseModel):
    name: str
    group1_label: str = "Patients PCBP1"
    group2_label: str = "Contrôles"
    group1_samples: list[str] = []
    group2_samples: list[str] = []
    mutated_genes: list[GeneEntry] = []


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    error_message: str | None = None
    mutated_genes: list[Any] = []
    created_at: datetime
    updated_at: datetime
    sample_groups: list[SampleGroupResponse] = []

    model_config = {"from_attributes": True}


class AnalysisListItem(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    mutated_genes: list[Any] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    analysis_id: uuid.UUID
    status: str
    event_count: int
