import json
import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Emits one structured JSON log line per request.

    Fields logged:
      trace_id   — unique per request; also set as X-Trace-ID response header
      method     — HTTP verb
      endpoint   — URL path
      store_id   — path param when present (null otherwise)
      status_code
      latency_ms
      event_count — populated by the ingest endpoint via request.state.event_count
    """

    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        start = time.monotonic()

        response = await call_next(request)

        latency_ms = round((time.monotonic() - start) * 1000, 2)

        logger.info(
            json.dumps(
                {
                    "trace_id": trace_id,
                    "method": request.method,
                    "endpoint": request.url.path,
                    "store_id": request.path_params.get("store_id"),
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "event_count": getattr(request.state, "event_count", None),
                }
            )
        )

        response.headers["X-Trace-ID"] = trace_id
        return response
