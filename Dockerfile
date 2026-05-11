FROM nvidia/cuda:12.4.1-base-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-dev python3.10-venv \
        git tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create virtual env
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install project dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" && \

# Copy project code
COPY configs/ configs/
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/
COPY README.md ./

# Build verification
RUN python -m pytest -q && echo "[✓] Build verification passed"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DASHSCOPE_API_KEY=

VOLUME ["/data", "/app/logs"]

ENTRYPOINT ["tini", "--"]
CMD ["python", "scripts/demo_session.py"]
