#!/bin/bash
set -e

echo "Waiting for database to be ready..."
until python3 -c "
import psycopg2, os, sys
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

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
