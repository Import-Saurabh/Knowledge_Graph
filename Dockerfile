# ============================================================================
# DriftForge — Multi-stage Dockerfile
# ============================================================================
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps required for building wheels (lxml, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Production runtime
FROM python:3.11-slim

WORKDIR /app

# Install only runtime system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source (respect .dockerignore)
COPY . .

# Ensure data directory exists (will be overridden by volume mount)
RUN mkdir -p /app/data

# Create non-root user for security
RUN groupadd -r driftforge && useradd -r -g driftforge -s /sbin/nologin driftforge \
    && chown -R driftforge:driftforge /app
USER driftforge

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
