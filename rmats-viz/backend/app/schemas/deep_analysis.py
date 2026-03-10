from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class DeepAnalysisCreate(BaseModel):
    """Request body for creating a new deep analysis."""

    name: str | None = Field(None, description="Optional name; auto-generated if omitted")
    fdr_threshold: float = Field(0.05, ge=0, le=1)
    pvalue_threshold: float | None = Field(None, ge=0, le=1)
    delta_psi_min: float = Field(0.1, ge=0, le=1)
    modules: list[str] = Field(default_factory=list)


class DeepAnalysisResponse(BaseModel):
    """Full deep analysis detail."""

    id: uuid.UUID
    analysis_id: uuid.UUID
    name: str
    status: str
    fdr_threshold: float
    pvalue_threshold: float | None = None
    delta_psi_min: float
    modules: list[str]
    n_significant: int
    n_not_significant: int
    permutation_iterations: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeepAnalysisListItem(BaseModel):
    """Lightweight item for listing deep analyses."""

    id: uuid.UUID
    name: str
    status: str
    fdr_threshold: float
    delta_psi_min: float
    n_significant: int
    n_not_significant: int
    created_at: datetime

    model_config = {"from_attributes": True}
