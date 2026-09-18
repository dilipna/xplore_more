# syntax=docker/dockerfile:1.7
# Build context: repository root (uv workspace).
#
# A thin httpx client of the public REST API -- no database driver, no ML model, so this image
# has none of the indexer/API image's weight (no fastembed bake-in needed).

FROM ghcr.io/astral-sh/uv:0.11.23 AS uv

FROM python:3.13-slim AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/mcp/ apps/mcp/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package xm-mcp --no-editable

FROM python:3.13-slim
RUN useradd --system --uid 10001 xm
COPY --from=build --chown=xm:xm /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 XM_MCP_HOST=0.0.0.0 XM_MCP_PORT=8080
WORKDIR /app
USER xm
EXPOSE 8080
ENTRYPOINT ["xm-mcp"]
