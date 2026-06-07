#!/bin/sh
set -e
cd /app/backend
export PYTHONPATH=/app

if [ -f /app/backend/.env.docker ]; then
  cp /app/backend/.env.docker /app/backend/.env
elif [ -f /app/backend/.env.docker.example ]; then
  cp /app/backend/.env.docker.example /app/backend/.env
fi

echo "Running database migrations..."
if ! alembic upgrade head; then
  echo "FATAL: alembic upgrade head failed — aborting startup" >&2
  exit 1
fi

echo "Running seed..."
if ! python -m src.seed.run; then
  echo "FATAL: demo seed failed — aborting startup" >&2
  exit 1
fi

echo "Starting API server..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
