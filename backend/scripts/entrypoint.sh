#!/bin/sh
set -e
cd /app/backend
export PYTHONPATH=/app

if [ -f /app/backend/.env.docker ] && [ ! -f /app/backend/.env ]; then
  cp /app/backend/.env.docker /app/backend/.env
elif [ -f /app/backend/.env.docker ]; then
  cp /app/backend/.env.docker /app/backend/.env
fi

echo "Running database migrations..."
alembic upgrade head

echo "Running seed..."
python -m src.seed.run

echo "Starting API server..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
