# syntax=docker/dockerfile:1
# API image. Build context is the repository root.

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra api

COPY libs/ ./libs/
COPY services/ ./services/
RUN uv sync --frozen --no-dev --extra api

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 atlas && chown -R atlas:atlas /app
USER atlas

EXPOSE 8080
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
