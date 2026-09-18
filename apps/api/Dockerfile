# syntax=docker/dockerfile:1.7
# Build context: repository root (uv workspace).

FROM ghcr.io/astral-sh/uv:0.11.23 AS uv

FROM python:3.13-slim AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/api/ apps/api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package xm-api --no-editable
# Bake in the embedding model: query embedding is on the request path, so a cold start must
# not wait on a model download, and the artifact is pinned per image digest (as for the indexer).
ENV XM_EMBEDDING_CACHE_DIR=/app/models
RUN /app/.venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/models')"

FROM python:3.13-slim
RUN useradd --system --uid 10001 xm
COPY --from=build --chown=xm:xm /app/.venv /app/.venv
COPY --from=build --chown=xm:xm /app/models /app/models
COPY config/entities.yaml /app/config/entities.yaml
ENV PATH=/app/.venv/bin:$PATH XM_EMBEDDING_CACHE_DIR=/app/models PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
USER xm
EXPOSE 8080
# xm-api reads PORT (Cloud Run sets it) and warms the embedder before serving, so the
# readiness probe only passes once the first query would be fast.
ENTRYPOINT ["xm-api"]
