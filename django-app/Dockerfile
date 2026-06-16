# ================================
# Dockerfile — Django App (Gunicorn + WhiteNoise)
# Serves the CXR Audit web UI on port 8000
# ================================

FROM python:3.11-slim AS builder

WORKDIR /app

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=lunit_audit.settings

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    pip install --no-cache-dir --prefix=/install gunicorn whitenoise

FROM python:3.11-slim AS runtime

WORKDIR /app

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=lunit_audit.settings

# Copy installed Python dependencies from the builder stage.
COPY --from=builder /install /usr/local

# Copy application code
COPY manage.py .
COPY lunit_audit/ lunit_audit/
COPY upload/ upload/
COPY viewer/ viewer/
COPY report/ report/
COPY gt/ gt/
COPY audit/ audit/
COPY templates/ templates/
COPY static/ static/

# Create directories for data that will be volume-mounted
RUN mkdir -p /app/db /app/media /app/staticfiles /app/audit_artifacts

# Create non-root user and grant ownership of writable directories
RUN adduser --disabled-password --no-create-home appuser && \
    chown -R appuser:appuser /app/db /app/media /app/staticfiles /app/audit_artifacts

# Copy entrypoint
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Expose Django/Gunicorn port
EXPOSE 8000

# Entrypoint runs as root to fix volume permissions,
# then drops to appuser for Django commands and Gunicorn.
ENTRYPOINT ["./entrypoint.sh"]
