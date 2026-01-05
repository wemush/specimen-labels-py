# syntax=docker/dockerfile:1

# WOLS CLI Container Image
# Multi-stage build for minimal image size

# Build stage - install dependencies
FROM python:3.13-slim AS builder

# Install uv for fast package installation
<<<<<<< Updated upstream
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
=======
# Pin to specific version for reproducibility and security
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /uvx /bin/
>>>>>>> Stashed changes

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Create virtual environment and install package with all extras
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python ".[all]"

# Runtime stage - minimal image
FROM python:3.13-slim AS runtime

# Install system dependencies for pyzbar (QR scanning)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libzbar0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set up PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash wols
USER wols
WORKDIR /home/wols

# Set entrypoint to the wols CLI
ENTRYPOINT ["wols"]
CMD ["--help"]

# Labels for container metadata
LABEL org.opencontainers.image.title="WOLS CLI"
LABEL org.opencontainers.image.description="WeMush Open Labeling Standard CLI for specimen tracking"
LABEL org.opencontainers.image.url="https://github.com/wemush/specimen-labels-py"
LABEL org.opencontainers.image.source="https://github.com/wemush/specimen-labels-py"
LABEL org.opencontainers.image.vendor="WeMush"
LABEL org.opencontainers.image.licenses="Apache-2.0"
