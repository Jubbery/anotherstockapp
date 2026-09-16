# syntax=docker/dockerfile:1
# Engine image. Build context is the repository root.
#   docker build -f ops/docker/engine.Dockerfile .

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

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

# R-11.1.a: deliberately NOT set here. The value comes from the Fly app config so
# that an image built for paper cannot be promoted to live by re-tagging it.
# A container started without ALPACA_ENV exits 78 before opening a socket.

CMD ["python", "-m", "services.engine"]
