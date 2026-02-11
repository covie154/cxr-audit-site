#!/bin/bash
set -e

echo "🫁 PRIMER-LLM Django — Starting up..."

# Run migrations
echo "📦 Running database migrations..."
python manage.py migrate --noinput

# Collect static files (WhiteNoise serves them from STATIC_ROOT)
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser from env vars if it doesn't exist
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
    echo "👤 Ensuring superuser exists..."
    python manage.py createsuperuser --noinput 2>/dev/null || true
fi

echo "✅ Starting Gunicorn on port 8000..."
exec gunicorn lunit_audit.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile -
