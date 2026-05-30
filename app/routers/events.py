import logging
from typing import Any, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion import process_ingest
from app.schemas import IngestResponse

logger = logging.getLogger("api.events")
router = APIRouter()

MAX_BATCH_SIZE = 500


@router.post("/events/ingest", response_model=IngestResponse, tags=["events"])
def ingest(
    request: Request,
    raw_events: List[Any] = Body(...),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """
    Ingest a batch of behavioural events from the detection pipeline.

    - Accepts up to 500 events per request.
    - Idempotent: the same event_id posted twice is stored once.
    - Partial success: valid events are accepted even if others in the batch
      are malformed.  Malformed events are reported in the errors list.
    - Never returns 5xx for malformed payloads — always 200 with a
      structured response showing accepted and rejected counts.
    """
    if len(raw_events) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Batch size {len(raw_events)} exceeds the maximum of "
                f"{MAX_BATCH_SIZE} events per request."
            ),
        )

    result = process_ingest(raw_events, db)

    # Expose accepted count to the logging middleware (logged as event_count)
    request.state.event_count = result.accepted

    return result
