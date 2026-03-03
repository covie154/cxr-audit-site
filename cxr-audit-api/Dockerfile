# ================================
# Dockerfile — CXR Audit API (FastAPI + Uvicorn)
# Runs combined_server.py --api-only on port 1221
# ================================

FROM python:3.11-slim

WORKDIR /app

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MPLCONFIGDIR=/app/tmp/matplotlib

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer)
COPY api_requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY cxr_audit/ cxr_audit/
COPY class_process_carpl.py .
COPY combined_server.py .
COPY open_protected_xlsx.py .

# Copy JSON configuration files
COPY padchest_op.json .
COPY padchest_tubes_lines.json .
COPY diagnoses.json .

# Create writable directory for intermediate files
RUN mkdir -p /app/tmp

# Create non-root user and grant ownership of writable dirs
RUN adduser --disabled-password --no-create-home appuser && \
    chown -R appuser:appuser /app/tmp

# Expose API port
EXPOSE 1221

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:1221/')" || exit 1

# Run API-only mode
CMD ["python", "combined_server.py", "--api-only"]
