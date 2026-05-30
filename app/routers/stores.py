import logging
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.anomalies import get_anomalies
from app.db import get_db
from app.funnel import get_funnel
from app.metrics import get_heatmap, get_metrics
from app.schemas import (
    AnomaliesResponse,
    FunnelStage,
    HeatmapResponse,
    MetricsResponse,
)

logger = logging.getLogger("api.stores")
router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("/{store_id}/metrics", response_model=MetricsResponse)
def metrics(store_id: str, db: Session = Depends(get_db)) -> MetricsResponse:
    """
    Today's real-time store metrics.

    - unique_visitors: non-staff visitors who entered today
    - conversion_rate: fraction who purchased (POS 5-min window correlation)
    - avg_dwell_by_zone: {zone_id → avg dwell ms} from ZONE_DWELL events
    - queue_depth: people currently in the billing area
    - abandonment_rate: fraction of billing queue joins that didn't convert

    Excludes is_staff=true visitors from all counts.
    Zero-purchase stores return conversion_rate=0.0 — never null or 500.
    """
    return get_metrics(store_id, db)


@router.get("/{store_id}/funnel", response_model=List[FunnelStage])
def funnel(store_id: str, db: Session = Depends(get_db)) -> List[FunnelStage]:
    """
    Conversion funnel: Entry → Zone Visit → Billing Queue → Purchase.

    The unit is the SESSION (visitor), not raw events.
    A visitor who re-enters the store counts as one entry in the funnel —
    COUNT(DISTINCT visitor_id) handles re-entry deduplication.

    drop_off_pct on each stage is the % who left between that stage and the
    previous one (0.0 on the first stage).
    """
    return get_funnel(store_id, db)


@router.get("/{store_id}/heatmap", response_model=HeatmapResponse)
def heatmap(store_id: str, db: Session = Depends(get_db)) -> HeatmapResponse:
    """
    Zone visit frequency and average dwell, normalized 0–100 for grid rendering.

    data_confidence = "low" when fewer than 20 unique visitor sessions exist
    for today — heatmap values are statistically unreliable at small sample sizes.
    """
    return get_heatmap(store_id, db)


@router.get("/{store_id}/anomalies", response_model=AnomaliesResponse)
def anomalies(store_id: str, db: Session = Depends(get_db)) -> AnomaliesResponse:
    """
    Active operational anomalies for this store.

    Detects:
      QUEUE_SPIKE     — current billing depth > 2× 7-day same-hour average
      CONVERSION_DROP — today's conversion rate < 80% of 7-day trailing average
      DEAD_ZONE       — product zone with no ZONE_ENTER in the last 30 minutes

    Each anomaly carries severity (INFO / WARN / CRITICAL) and a suggested_action.
    Empty list means no anomalies detected — never an error.
    """
    return get_anomalies(store_id, db)
