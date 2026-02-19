from __future__ import annotations
import uuid
from pydantic import BaseModel


class SplicingEventResponse(BaseModel):
    id: uuid.UUID
    analysis_id: uuid.UUID
    event_type: str
    rmats_id: int | None = None
    gene_id: str | None = None
    gene_symbol: str | None = None
    chr: str | None = None
    strand: str | None = None
    exon_start: int | None = None
    exon_end: int | None = None
    upstream_es: int | None = None
    upstream_ee: int | None = None
    downstream_es: int | None = None
    downstream_ee: int | None = None
    second_exon_start: int | None = None
    second_exon_end: int | None = None
    ijc_sample_1: str | None = None
    sjc_sample_1: str | None = None
    ijc_sample_2: str | None = None
    sjc_sample_2: str | None = None
    p_value: float | None = None
    fdr: float | None = None
    inc_level_1: str | None = None
    inc_level_2: str | None = None
    inc_level_difference: float | None = None
    abs_inc_level_diff: float | None = None
    top_rank: int | None = None

    model_config = {"from_attributes": True}


class EventsPage(BaseModel):
    items: list[SplicingEventResponse]
    total: int
    page: int
    page_size: int
    pages: int
