"""
Pydantic schemas — the single source of truth for the event contract.

Separation of concerns:
  app/models.py   — SQLAlchemy ORM (what the database looks like)
  app/schemas.py  — Pydantic (what the API accepts and returns)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Event type catalogue
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    ENTRY                 = "ENTRY"
    EXIT                  = "EXIT"
    ZONE_ENTER            = "ZONE_ENTER"
    ZONE_EXIT             = "ZONE_EXIT"
    ZONE_DWELL            = "ZONE_DWELL"
    BILLING_QUEUE_JOIN    = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY               = "REENTRY"


# Event types where zone_id MUST be null
_NULL_ZONE_TYPES = {EventType.ENTRY, EventType.EXIT, EventType.REENTRY}

# Event types where zone_id MUST be present
_ZONE_REQUIRED_TYPES = {
    EventType.ZONE_ENTER,
    EventType.ZONE_EXIT,
    EventType.ZONE_DWELL,
    EventType.BILLING_QUEUE_JOIN,
    EventType.BILLING_QUEUE_ABANDON,
}


# ---------------------------------------------------------------------------
# Event schema
# ---------------------------------------------------------------------------

class EventMetadata(BaseModel):
    queue_depth: Optional[int] = Field(default=None)
    sku_zone: Optional[str] = Field(default=None, max_length=64)
    session_seq: int = Field(ge=1)


class StoreEvent(BaseModel):
    event_id: UUID
    store_id: str = Field(min_length=1, max_length=32)
    camera_id: str = Field(min_length=1, max_length=32)
    visitor_id: str = Field(min_length=1, max_length=32)
    event_type: EventType
    timestamp: datetime
    zone_id: Optional[str] = Field(default=None, max_length=64)
    dwell_ms: int = Field(ge=0, default=0)
    is_staff: bool
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: EventMetadata

    @model_validator(mode="after")
    def validate_event_type_rules(self) -> "StoreEvent":
        # ENTRY / EXIT / REENTRY must not carry a zone
        if self.event_type in _NULL_ZONE_TYPES and self.zone_id is not None:
            raise ValueError(
                f"{self.event_type} events must have zone_id=null, got '{self.zone_id}'"
            )

        # Zone-level events must carry a zone
        if self.event_type in _ZONE_REQUIRED_TYPES and not self.zone_id:
            raise ValueError(
                f"{self.event_type} events must have a non-null zone_id"
            )

        # BILLING_QUEUE_JOIN must carry a queue depth of at least 1
        if self.event_type == EventType.BILLING_QUEUE_JOIN:
            qd = self.metadata.queue_depth
            if qd is None or qd < 1:
                raise ValueError(
                    "BILLING_QUEUE_JOIN requires metadata.queue_depth >= 1"
                )

        return self


# ---------------------------------------------------------------------------
# Ingest request / response
# ---------------------------------------------------------------------------

class IngestError(BaseModel):
    event_id: str   # str, not UUID — may be missing or malformed in the raw payload
    reason: str


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: List[IngestError]


# ---------------------------------------------------------------------------
# GET /stores/{id}/metrics
# ---------------------------------------------------------------------------

class MetricsResponse(BaseModel):
    store_id: str
    date: str
    unique_visitors: int
    conversion_rate: float          # 0.0 – 1.0
    avg_dwell_by_zone: dict         # {zone_id: avg_dwell_ms}
    queue_depth: int                # current people in billing area
    abandonment_rate: float         # 0.0 – 1.0
    computed_at: str


# ---------------------------------------------------------------------------
# GET /stores/{id}/funnel
# ---------------------------------------------------------------------------

class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float             # % who left between previous and this stage


# ---------------------------------------------------------------------------
# GET /stores/{id}/heatmap
# ---------------------------------------------------------------------------

class ZoneHeatmap(BaseModel):
    zone_id: str
    visit_count: int
    avg_dwell_ms: float
    normalized_score: float         # 0 – 100, relative to busiest zone


class HeatmapResponse(BaseModel):
    store_id: str
    data_confidence: str            # "ok" | "low" (< 20 sessions in window)
    zones: List[ZoneHeatmap]
    computed_at: str


# ---------------------------------------------------------------------------
# GET /stores/{id}/anomalies
# ---------------------------------------------------------------------------

class Anomaly(BaseModel):
    type: str
    severity: str                   # INFO | WARN | CRITICAL
    suggested_action: str
    detected_at: str
    details: dict


class AnomaliesResponse(BaseModel):
    store_id: str
    anomalies: List[Anomaly]
    computed_at: str
