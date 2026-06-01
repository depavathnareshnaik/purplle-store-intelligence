#!/bin/bash
set -e

echo "Waiting for database to be ready..."
until python3 -c "
import os, sys
db_url = os.environ.get('DATABASE_URL', '')
if db_url:
    import psycopg2
    try:
        psycopg2.connect(db_url, connect_timeout=3).close()
        print('Database ready (via DATABASE_URL)!')
        sys.exit(0)
    except Exception as e:
        print(f'DB not ready: {e}')
        sys.exit(1)
else:
    import psycopg2
    try:
        psycopg2.connect(
            host=os.environ.get('POSTGRES_HOST','postgres'),
            port=os.environ.get('POSTGRES_PORT','5432'),
            dbname=os.environ.get('POSTGRES_DB','store_intelligence'),
            user=os.environ.get('POSTGRES_USER','postgres'),
            password=os.environ.get('POSTGRES_PASSWORD','postgres'),
            connect_timeout=3
        ).close()
        print('Database ready!')
        sys.exit(0)
    except Exception as e:
        print(f'DB not ready: {e}')
        sys.exit(1)
" 2>/dev/null; do
    echo "  ... retrying in 3s"
    sleep 3
done

echo "Running database migrations..."
alembic upgrade head

echo "Auto-ingesting events if database is empty..."
python3 -c "
import json, sys
from pathlib import Path
from app.db import SessionLocal
from app.ingestion import process_ingest
from sqlalchemy import text

db = SessionLocal()
try:
    count = db.execute(text(\"SELECT COUNT(*) FROM events WHERE store_id='STORE_BLR_002'\")).scalar()
    if count and count > 0:
        print(f'DB already has {count} events, skipping auto-ingest')
        sys.exit(0)
    path = Path('data/events/STORE_BLR_002.jsonl')
    if not path.exists():
        print('No events file found')
        sys.exit(0)
    events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    result = process_ingest(events, db)
    print(f'Auto-ingested: accepted={result.accepted}')
finally:
    db.close()
" || echo "Auto-ingest step failed (non-fatal, continuing)"

echo "Starting API server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
