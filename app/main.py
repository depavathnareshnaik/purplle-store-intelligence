import json
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.exceptions import sqlalchemy_exception_handler, unhandled_exception_handler
from app.middleware import RequestLoggingMiddleware
from app.dashboard.ws import router as dashboard_router
from app.pos_loader import load_pos_transactions
from app.routers import events, health, stores

settings = get_settings()


# ---------------------------------------------------------------------------
# Logging — every log line is a JSON object so log aggregators can index fields
# ---------------------------------------------------------------------------

class _JSONFormatter(logging.Formatter):
    """
    Wraps each log record as a flat JSON object.
    If the message itself is already valid JSON (emitted by middleware/health)
    it is merged in rather than nested under a "message" key.
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload = json.loads(record.getMessage())
        except (json.JSONDecodeError, TypeError):
            payload = {"message": record.getMessage()}

        return json.dumps(
            {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                **payload,
            }
        )


_LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "app.main._JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        # Uvicorn access log is already captured by our middleware; suppress the duplicate
        "uvicorn.access": {"level": "WARNING", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
    },
}


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.config.dictConfig(_LOGGING_CONFIG)
    logging.getLogger("api.startup").info(
        json.dumps(
            {
                "message": "startup",
                "service": settings.APP_NAME,
                "version": settings.APP_VERSION,
            }
        )
    )
    # Load POS transactions from CSV so conversion rate is queryable from first request
    load_pos_transactions()
    yield
    logging.getLogger("api.startup").info(
        json.dumps({"message": "shutdown", "service": settings.APP_NAME})
    )


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware — runs for every request in registration order (last registered = outermost)
    app.add_middleware(RequestLoggingMiddleware)

    # Exception handlers — no raw stack traces in responses
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Routers
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(stores.router)
    app.include_router(dashboard_router)   # GET /dashboard + WS /ws/{store_id}

    return app


app = create_app()
