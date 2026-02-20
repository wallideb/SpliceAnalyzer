from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


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
    mutated_genes: list[str] = []


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    error_message: str | None = None
    mutated_genes: list[str] = []
    created_at: datetime
    updated_at: datetime
    sample_groups: list[SampleGroupResponse] = []

    model_config = {"from_attributes": True}


class AnalysisListItem(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    mutated_genes: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    analysis_id: uuid.UUID
    status: str
    event_count: int
