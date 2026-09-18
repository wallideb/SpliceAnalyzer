"""
Analysis schemas
================
Pydantic models for analysis listing, detailed responses and the upload result.

``mutated_genes`` is stored as a JSONB list of ``GeneEntry``-shaped objects
(see :mod:`app.schemas.gene`):
    [{"symbol": "BRCA1", "ensembl_id": "ENSG00000012048", "display": "BRCA1 (ENSG00000012048)"}]

Analysis creation uses multipart form fields (see ``routers/analyses.py``),
so there is no JSON request body schema here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SampleGroupResponse(BaseModel):
    id: uuid.UUID
    group_label: str
    group_index: int
    sample_names: list[str]

    model_config = {"from_attributes": True}


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
    # Human-readable notes about the import (e.g. "no events imported").
    warnings: list[str] = []
