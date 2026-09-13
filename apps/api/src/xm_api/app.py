"""XploreMore public read API.

Latency: every search response carries a Server-Timing header (embed, lexical, dense,
fusion, hydrate), so the latency budget in docs/search.md is observable from any client
and from load tests without extra tooling.

Degradation: if the embedding model fails, search answers lexical-only and says so in
`degraded` and in `X-XM-Degraded`, rather than failing the request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from xm_api.schemas import FeedResponse, SearchResponse, StoryDetail
from xm_api.stories import recent_story_ids, story_articles, summaries
from xm_cluster.entities import Gazetteer
from xm_core.db.session import make_engine, make_sessionmaker
from xm_core.settings import Settings, get_settings
from xm_embed.embedder import FastEmbedEmbedder, QueryEmbedder
from xm_rank.features import FEATURE_VERSION, heuristic_importance, story_features
from xm_search.query import parse_query
from xm_search.retrieval import RetrievalTrace, retrieve_stories

log = logging.getLogger("xm_api")

FEED_CANDIDATES = 500


@dataclass
class AppState:
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    gazetteer: Gazetteer
    embedder: QueryEmbedder | None


def _state(request: Request) -> AppState:
    return request.app.state.xm


# Module level on purpose: with postponed annotations FastAPI resolves dependency types by
# name at import scope; a type alias defined inside create_app() would silently turn `st`
# into a required query parameter (422).
StateDep = Annotated[AppState, Depends(_state)]


def create_app(
    settings: Settings | None = None,
    *,
    embedder: QueryEmbedder | None = None,
    warm_embedder: bool = True,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings)
        model = embedder
        if model is None:
            model = FastEmbedEmbedder(
                settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir
            )
            if warm_embedder:
                await asyncio.to_thread(model.warm)  # pay model load before accepting traffic
        app.state.xm = AppState(
            engine=engine,
            sessionmaker=make_sessionmaker(engine),
            gazetteer=Gazetteer.load(Path(settings.entities_file)),
            embedder=model,
        )
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="XploreMore API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}  # liveness: process only, never dependencies

    @app.get("/readyz", include_in_schema=False)
    async def readyz(st: StateDep) -> dict[str, str]:
        try:
            async with st.sessionmaker() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:  # readiness must fail closed on any dependency error
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        return {"status": "ready"}

    @app.get("/v1/search", response_model=SearchResponse)
    async def search(
        st: StateDep,
        response: Response,
        q: Annotated[str, Query(min_length=1, max_length=256)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> SearchResponse:
        timings: dict[str, float] = {}
        parsed = parse_query(q, st.gazetteer)
        if parsed.is_empty:
            return SearchResponse(query=q, results=[], degraded=[])

        embedding: list[float] | None = None
        t0 = time.perf_counter()
        if st.embedder is not None:
            try:
                embedding = await asyncio.to_thread(st.embedder.embed_query, parsed.text)
            except Exception:
                log.exception("query embedding failed; serving lexical-only")
        timings["embed"] = (time.perf_counter() - t0) * 1000

        trace = RetrievalTrace()
        async with st.sessionmaker() as session:
            hits = await retrieve_stories(session, parsed, embedding, limit=limit, trace=trace)
            t1 = time.perf_counter()
            results = await summaries(
                session, [h.story_id for h in hits], {h.story_id: h.score for h in hits}
            )
            timings["hydrate"] = (time.perf_counter() - t1) * 1000
        timings |= {"lexical": trace.lexical_ms, "dense": trace.dense_ms, "fusion": trace.fusion_ms}

        response.headers["Server-Timing"] = ", ".join(f"{k};dur={v:.1f}" for k, v in timings.items())
        if trace.degraded:
            response.headers["X-XM-Degraded"] = ",".join(trace.degraded)
        return SearchResponse(query=q, results=results, degraded=trace.degraded)

    @app.get("/v1/feed", response_model=FeedResponse)
    async def feed(
        st: StateDep,
        response: Response,
        limit: Annotated[int, Query(ge=1, le=50)] = 30,
        window_hours: Annotated[int, Query(ge=1, le=24 * 14)] = 72,
    ) -> FeedResponse:
        now = datetime.now(UTC)
        async with st.sessionmaker() as session:
            candidates = await recent_story_ids(session, now - timedelta(hours=window_hours), FEED_CANDIDATES)
            features = await story_features(session, candidates, now)
            scores = {sid: heuristic_importance(f) for sid, f in features.items()}
            ranked = sorted(scores, key=lambda sid: (-scores[sid], sid))[:limit]
            results = await summaries(session, ranked, scores)
        response.headers["Cache-Control"] = "public, max-age=60"
        return FeedResponse(ranker=f"heuristic/{FEATURE_VERSION}", results=results)

    @app.get("/v1/stories/{story_id}", response_model=StoryDetail)
    async def story(st: StateDep, story_id: int) -> StoryDetail:
        async with st.sessionmaker() as session:
            found = await summaries(session, [story_id])
            if not found:
                raise HTTPException(status_code=404, detail="story not found")
            return StoryDetail(story=found[0], articles=await story_articles(session, story_id))

    return app
