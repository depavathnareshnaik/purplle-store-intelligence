import json
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("api.exceptions")


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """
    Maps any SQLAlchemy error to HTTP 503.
    Raw exception details are logged server-side but never sent to the client
    — prevents leaking table names, query structure, or stack traces.
    """
    trace_id = getattr(request.state, "trace_id", "unknown")
    logger.error(
        json_line(
            {
                "message": "database error",
                "trace_id": trace_id,
                "path": request.url.path,
                "error_type": type(exc).__name__,
            }
        )
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": "SERVICE_UNAVAILABLE",
            "detail": "The database is temporarily unavailable. Please retry.",
            "trace_id": trace_id,
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catches anything not already handled.
    Returns 500 with no stack trace in the response body.
    """
    trace_id = getattr(request.state, "trace_id", "unknown")
    logger.error(
        json_line(
            {
                "message": "unhandled error",
                "trace_id": trace_id,
                "path": request.url.path,
                "error_type": type(exc).__name__,
            }
        )
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected error occurred.",
            "trace_id": trace_id,
        },
    )


def json_line(data: dict) -> str:
    return json.dumps(data)
