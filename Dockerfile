# syntax=docker/dockerfile:1
FROM python:3.10-slim

WORKDIR /app

# ── Install system dependencies ──────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies (cached unless pyproject.toml changes) ───────
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# ── Copy application code ────────────────────────────────────────────────────
COPY configs/ configs/
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/
COPY README.md ./

# ── Build verification: run tests ────────────────────────────────────────────
RUN python -m pytest -q && echo "[✓] Build verification passed"

# ── Runtime config ───────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DASHSCOPE_API_KEY=

# Volume for parquet data and output logs
VOLUME ["/data", "/app/logs"]

ENTRYPOINT ["tini", "--"]

# Default: run demo (works without API key, verifies end-to-end pipeline)
CMD ["python", "scripts/demo_session.py"]
