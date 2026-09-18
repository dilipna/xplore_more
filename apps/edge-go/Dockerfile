# syntax=docker/dockerfile:1.7
# Build context: repository root (the image embeds config/sources.yaml and problem_sources.yaml).

FROM golang:1.27-alpine AS build
WORKDIR /src
COPY apps/edge-go/go.mod apps/edge-go/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY apps/edge-go/ ./
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ingestor ./cmd/ingestor && \
    CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/poller ./cmd/poller

# Distroless static: no shell, no package manager, CA certificates included, runs as nonroot.
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/ /app/
COPY config/sources.yaml /app/config/sources.yaml
COPY config/problem_sources.yaml /app/config/problem_sources.yaml
ENV XM_SOURCES_FILE=/app/config/sources.yaml
USER nonroot:nonroot
ENTRYPOINT ["/app/ingestor"]
