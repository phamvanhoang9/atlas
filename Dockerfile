# =============================================================================
# STAGE 1: Builder - Install dependencies in a temporary layer
# =============================================================================
FROM python:3.12-slim-bookworm AS builder

ARG CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-12-v2

# Set environment variables for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    CROSS_ENCODER_MODEL=${CROSS_ENCODER_MODEL} \
    HF_HOME=/opt/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/opt/models/sentence-transformers

# Install build dependencies (will be discarded after this stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for isolated dependency management
RUN python -m venv /opt/venv

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy only requirements file first for better layer caching
# (Dependencies change less frequently than application code)
COPY requirements.txt .

# Install Python dependencies in the virtual environment
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt 

# Production image embeds the local reranker model so runtime does not need
# network access for cross-encoder reranking.
RUN pip install sentence-transformers==3.3.1 && \
    mkdir -p /opt/models && \
    python -c "import os; from sentence_transformers import CrossEncoder; CrossEncoder(os.environ['CROSS_ENCODER_MODEL'])"

# =============================================================================
# STAGE 2: Runtime - Minimal production image
# =============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Metadata labels for image identification and maintenance
LABEL maintainer="ATLAS Team" \
      description="Agentic Task & Literature Analysis System" \
      version="1.0" \
      python.version="3.12"

# Set production environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ATLAS_ENV=production \
    HF_HOME=/opt/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/opt/models/sentence-transformers \
    CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-12-v2 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1

# Install runtime dependencies only (minimal set)
# - ca-certificates: For HTTPS requests
# - libgomp1: OpenMP library (needed by some ML libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create a non-root user with specific UID/GID for security
# Using UID 1000 is conventional for containerized applications
RUN groupadd -g 1000 atlas && \
    useradd -u 1000 -g atlas -s /bin/bash -m atlas

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/models /opt/models

# Copy application code with proper ownership
# This ensures the non-root user can access all files
COPY --chown=atlas:atlas . .

# Create outputs directory with proper permissions
RUN mkdir -p /app/outputs && \
    mkdir -p /app/.atlas_data /app/.atlas_cache && \
    chown -R atlas:atlas /app/outputs /app/.atlas_data /app/.atlas_cache /opt/models

# Switch to non-root user for security
USER atlas

# Expose the application port
EXPOSE 8000

# Health check to monitor container status
# Checks if the FastAPI application is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

# Default command to run the application
# Using uvicorn directly is more efficient than python main.py
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
