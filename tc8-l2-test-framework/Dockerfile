# Multi-stage build for production deployment
FROM python:3.11-slim as builder

# Install system dependencies for Scapy
RUN apt-get update && apt-get install -y \
    gcc \
    libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Production image
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpcap0.8 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 tc8user && \
    mkdir -p /app /app/config /app/data /app/reports /app/logs && \
    chown -R tc8user:tc8user /app

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=tc8user:tc8user src/ /app/src/
COPY --chown=tc8user:tc8user web/ /app/web/
COPY --chown=tc8user:tc8user config/ /app/config/
COPY --chown=tc8user:tc8user data/ /app/data/

# Switch to non-root user
USER tc8user

# Expose web UI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Default command: start web server
CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Alternative entrypoint for CLI usage:
# docker run tc8-l2-test-framework python -m src.cli run --dut /app/config/dut_profiles/my_ecu.yaml --tier smoke
