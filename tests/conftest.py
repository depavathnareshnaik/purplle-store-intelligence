# PROMPT: Create pytest fixtures for a FastAPI + PostgreSQL app.
# Need: isolated test DB, test client with dependency override, sample event factory.
# CHANGES MADE: Scope is "session" for engine (create tables once) and "function"
# for db_session (rollback after each test) so tests are independent without
# recreating the schema on every test.

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db import Base, get_db
from app.main import app

# Uses a separate test database to avoid touching production data.
# Override TEST_DATABASE_URL env var to point at a different host/db if needed.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/store_intelligence_test",
)


@pytest.fixture(scope="session")
def test_engine():
    """Creates the test database schema once for the entire test session."""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """
    Provides a database session that rolls back after each test.
    This keeps tests isolated without recreating the schema every time.
    """
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    FastAPI test client with the real database session overridden.
    Any code that calls get_db() receives the test session instead.
    """
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_event(**overrides) -> dict:
    """
    Factory for a minimal valid event dict. Override any field as needed.

    Timestamp defaults to NOW (UTC) so events always match the "today" filter
    used by /metrics, /funnel, and /heatmap without any manual date wrangling.

    Usage:
        event = make_event(event_type="EXIT", is_staff=True)
    """
    import uuid
    from datetime import datetime, timezone

    base = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "ENTRY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.91,
        "metadata": {
            "queue_depth": None,
            "sku_zone": None,
            "session_seq": 1,
        },
    }
    base.update(overrides)
    return base
