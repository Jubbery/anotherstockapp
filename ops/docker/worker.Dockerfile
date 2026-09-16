# syntax=docker/dockerfile:1
# Worker image. Build context is the repository root.
#
# Heavier than the other two: LightGBM needs libgomp, and DuckDB reads Parquet
# from Supabase Storage over httpfs (§6.3.3).

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY libs/ ./libs/
COPY services/ ./services/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 atlas && chown -R atlas:atlas /app
USER atlas

CMD ["python", "-m", "services.worker"]
