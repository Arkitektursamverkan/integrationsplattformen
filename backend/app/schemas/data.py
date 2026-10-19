"""Pydantic schemas for Data API responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DataRecordRead(BaseModel):
    id: uuid.UUID
    flow_id: uuid.UUID
    source_type: str
    external_id: str
    data: dict
    checksum: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataRecordList(BaseModel):
    records: list[DataRecordRead]
    total: int
    page: int
    page_size: int


class DataSourceSummary(BaseModel):
    flow_id: uuid.UUID
    flow_name: str
    connector_type: str
    record_count: int
    last_sync: datetime | None
    status: str
