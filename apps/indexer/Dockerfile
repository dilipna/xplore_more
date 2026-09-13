# syntax=docker/dockerfile:1.7
# Build context: repository root (uv workspace).

FROM ghcr.io/astral-sh/uv:0.11.23 AS uv

FROM python:3.13-slim AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/indexer/ apps/indexer/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package xm-indexer --no-editable
# Bake the embedding model into the image: no download on cold start, no runtime
# dependency on the model hub, and a pinned artifact per image digest.
ENV XM_EMBEDDING_CACHE_DIR=/app/models
RUN /app/.venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/models')"

FROM python:3.13-slim
RUN useradd --system --uid 10001 xm
COPY --from=build --chown=xm:xm /app/.venv /app/.venv
COPY --from=build --chown=xm:xm /app/models /app/models
COPY alembic.ini /app/alembic.ini
COPY config/entities.yaml /app/config/entities.yaml
ENV PATH=/app/.venv/bin:$PATH XM_EMBEDDING_CACHE_DIR=/app/models PYTHONUNBUFFERED=1
WORKDIR /app
USER xm
ENTRYPOINT ["xm-indexer"]
