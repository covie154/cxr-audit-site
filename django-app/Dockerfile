# ================================
# Dockerfile — Django App (Gunicorn + WhiteNoise)
# Serves the CXR Audit web UI on port 8000
# ================================

FROM python:3.11-slim

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
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn whitenoise

# Copy application code
COPY manage.py .
COPY lunit_audit/ lunit_audit/
COPY upload/ upload/
COPY viewer/ viewer/
COPY report/ report/
COPY gt/ gt/
COPY templates/ templates/
COPY static/ static/

# Create directories for data that will be volume-mounted
RUN mkdir -p /app/db /app/media /app/staticfiles

# Create non-root user and grant ownership of writable directories
RUN adduser --disabled-password --no-create-home appuser && \
    chown -R appuser:appuser /app/db /app/media /app/staticfiles

# Copy entrypoint
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Expose Django/Gunicorn port
EXPOSE 8000

# Switch to non-root user
USER appuser

ENTRYPOINT ["./entrypoint.sh"]
