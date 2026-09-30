"""XploreMore public read API.

Latency: every search response carries a Server-Timing header (embed, lexical, dense,
fusion, rerank when enabled, hydrate), so the latency budget in docs/search.md is observable from any client
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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as PathParam
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from xm_api.auth import HEADER as API_KEY_HEADER
from xm_api.auth import InvalidApiKeyError, KeyResolver, Principal
from xm_api.cache import ResponseCache
from xm_api.problems import RANKER, find_problems, get_problem
from xm_api.ratelimit import RateLimiter
from xm_api.schemas import (
    FeedResponse,
    FeedWeights,
    ProblemCategory,
    ProblemDetail,
    ProblemsResponse,
    RankSignals,
    SearchResponse,
    StatsResponse,
    StoryDetail,
)
from xm_api.stats import corpus_stats
from xm_api.stories import recent_story_ids, story_articles, summaries
from xm_cluster.entities import Gazetteer
from xm_core.db.session import make_engine, make_sessionmaker
from xm_core.settings import Settings, get_settings
from xm_embed.embedder import FastEmbedEmbedder, QueryEmbedder
from xm_rank.features import (
    DEFAULT_WEIGHTS,
    FEATURE_VERSION,
    HeuristicTerms,
    HeuristicWeights,
    StoryFeatures,
    diversify,
    heuristic_terms,
    lead_sources,
    story_features,
)
from xm_search.query import parse_query
from xm_search.rerank import TreeEnsemble, gather_signals, rerank
from xm_search.retrieval import RetrievalTrace, retrieve_stories

log = logging.getLogger("xm_api")

FEED_CANDIDATES = 500
FEED_RANKER = f"heuristic/{FEATURE_VERSION}+source-cap-v1"
RERANK_CANDIDATES = 50  # the reranker was trained to reorder the fused top 50


@dataclass
class AppState:
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    gazetteer: Gazetteer
    embedder: QueryEmbedder | None
    keys: KeyResolver
    limiter: RateLimiter
    cache: ResponseCache
    require_key_for_problems: bool
    reranker: TreeEnsemble | None = None


def _state(request: Request) -> AppState:
    return request.app.state.xm


def _signals(t: HeuristicTerms, f: StoryFeatures) -> RankSignals:
    return RankSignals(
        coverage=round(t.coverage, 4),
        authority=round(t.authority, 4),
        community=round(t.community, 4),
        freshness=round(t.freshness, 4),
        hn_points=f.hn_points_max,
        hours_since_published=round(f.hours_since_published, 2),
    )


def _mark_degraded(response: Response, reason: str) -> None:
    existing = [r for r in response.headers.get("X-XM-Degraded", "").split(",") if r]
    response.headers["X-XM-Degraded"] = ",".join([*existing, reason])


async def _protect(request: Request, response: Response) -> Principal:
    """Authenticate (optional key) and rate-limit every /v1 request."""
    st: AppState = request.app.state.xm
    client = request.client.host if request.client else "unknown"
    try:
        principal = await st.keys.resolve(request.headers.get(API_KEY_HEADER), client)
    except InvalidApiKeyError:
        raise HTTPException(
            status_code=401, detail="invalid or revoked API key", headers={"WWW-Authenticate": "ApiKey"}
        ) from None
    decision = await st.limiter.check(principal.kind, principal.id, principal.rate_per_minute)
    response.headers["RateLimit-Limit"] = str(decision.limit)
    response.headers["RateLimit-Remaining"] = str(decision.remaining)
    if decision.degraded:
        _mark_degraded(response, "rate_limit")
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                "RateLimit-Limit": str(decision.limit),
                "RateLimit-Remaining": "0",
            },
        )
    return principal


# Module level on purpose: with postponed annotations FastAPI resolves dependency types by
# name at import scope; a type alias defined inside create_app() would silently turn `st`
# into a required query parameter (422).
StateDep = Annotated[AppState, Depends(_state)]
ProtectedDep = Annotated[Principal, Depends(_protect)]


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
        sessionmaker = make_sessionmaker(engine)
        # Short timeouts: a slow Redis must not add latency; the limiter fails open instead.
        redis = Redis.from_url(
            settings.redis_url.get_secret_value(), socket_timeout=0.25, socket_connect_timeout=0.25
        )
        app.state.xm = AppState(
            engine=engine,
            sessionmaker=sessionmaker,
            gazetteer=Gazetteer.load(Path(settings.entities_file)),
            embedder=model,
            keys=KeyResolver(sessionmaker, settings.anon_rate_per_minute),
            limiter=RateLimiter(redis),
            cache=ResponseCache(
                redis,
                prefix=settings.response_cache_prefix,
                generation_key=settings.response_cache_generation_key,
                ttl_s=settings.response_cache_ttl_s,
            ),
            require_key_for_problems=settings.require_api_key_for_problems,
            reranker=TreeEnsemble.load(settings.search_reranker_file)
            if settings.search_reranker_file
            else None,
        )
        try:
            yield
        finally:
            await redis.aclose()
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
        _: ProtectedDep,
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

        # The reranker was trained with dense features, so lexical-only (degraded) requests skip it.
        reranker = st.reranker if embedding is not None else None
        trace = RetrievalTrace()
        async with st.sessionmaker() as session:
            depth = RERANK_CANDIDATES if reranker is not None else limit
            hits = await retrieve_stories(session, parsed, embedding, limit=depth, trace=trace)
            ids = [h.story_id for h in hits][:limit]
            scores = {h.story_id: h.score for h in hits}
            if reranker is not None and embedding is not None and hits:
                t_rr = time.perf_counter()
                signals = await gather_signals(session, parsed, embedding, hits, datetime.now(UTC))
                ranked = rerank(reranker, parsed, signals)[:limit]
                ids = [c.story_id for c, _ in ranked]
                scores = {c.story_id: score for c, score in ranked}
                timings["rerank"] = (time.perf_counter() - t_rr) * 1000
            t1 = time.perf_counter()
            results = await summaries(session, ids, scores)
            timings["hydrate"] = (time.perf_counter() - t1) * 1000
        timings |= {"lexical": trace.lexical_ms, "dense": trace.dense_ms, "fusion": trace.fusion_ms}

        response.headers["Server-Timing"] = ", ".join(f"{k};dur={v:.1f}" for k, v in timings.items())
        for reason in trace.degraded:
            _mark_degraded(response, reason)
        return SearchResponse(query=q, results=results, degraded=trace.degraded)

    @app.get("/v1/feed", response_model=FeedResponse)
    async def feed(
        st: StateDep,
        _: ProtectedDep,
        response: Response,
        limit: Annotated[int, Query(ge=1, le=50)] = 30,
        window_hours: Annotated[int, Query(ge=1, le=24 * 14)] = 72,
        # Reader-tunable heuristic weights, bounded; the defaults give the standard feed.
        w_sources: Annotated[float, Query(ge=0.0, le=3.0)] = DEFAULT_WEIGHTS.sources,
        w_authority: Annotated[float, Query(ge=0.0, le=3.0)] = DEFAULT_WEIGHTS.authority,
        w_points: Annotated[float, Query(ge=0.0, le=1.5)] = DEFAULT_WEIGHTS.hn_points,
        half_life_hours: Annotated[float, Query(ge=2.0, le=168.0)] = DEFAULT_WEIGHTS.half_life_hours,
    ) -> FeedResponse:
        weights = HeuristicWeights(
            sources=round(w_sources, 2),
            authority=round(w_authority, 2),
            hn_points=round(w_points, 2),
            half_life_hours=round(half_life_hours, 1),
        )

        async def compute() -> tuple[FeedResponse, bool]:
            now = datetime.now(UTC)
            async with st.sessionmaker() as session:
                candidates = await recent_story_ids(
                    session, now - timedelta(hours=window_hours), FEED_CANDIDATES
                )
                features = await story_features(session, candidates, now)
                terms = {sid: heuristic_terms(f, weights) for sid, f in features.items()}
                scores = {sid: t.score for sid, t in terms.items()}
                ranked = sorted(scores, key=lambda sid: (-scores[sid], sid))
                # No single source may fill the top of the feed (docs/reports/feed-diversity-v1.md).
                ranked = diversify(ranked, await lead_sources(session, ranked))[:limit]
                results = [
                    s.model_copy(update={"signals": _signals(terms[s.id], features[s.id])})
                    for s in await summaries(session, ranked, scores)
                ]
            body = FeedResponse(ranker=FEED_RANKER, weights=FeedWeights(**asdict(weights)), results=results)
            return body, True

        key = {"limit": limit, "window_hours": window_hours, **asdict(weights)}
        body, status = await st.cache.get_or_compute("feed", key, FeedResponse, compute)
        response.headers["X-XM-Cache"] = status
        response.headers["Cache-Control"] = "public, max-age=60"
        return body

    @app.get("/v1/stats", response_model=StatsResponse)
    async def stats(st: StateDep, _: ProtectedDep, response: Response) -> StatsResponse:
        async def compute() -> tuple[StatsResponse, bool]:
            async with st.sessionmaker() as session:
                return await corpus_stats(session, datetime.now(UTC)), True

        body, status = await st.cache.get_or_compute("stats", {}, StatsResponse, compute)
        response.headers["X-XM-Cache"] = status
        response.headers["Cache-Control"] = "public, max-age=60"
        return body

    @app.get("/v1/stories/{story_id}", response_model=StoryDetail)
    async def story(st: StateDep, _: ProtectedDep, story_id: int) -> StoryDetail:
        async with st.sessionmaker() as session:
            found = await summaries(session, [story_id])
            if not found:
                raise HTTPException(status_code=404, detail="story not found")
            return StoryDetail(story=found[0], articles=await story_articles(session, story_id))

    def _require_key(st: AppState, principal: Principal) -> None:
        if st.require_key_for_problems and principal.kind != "key":
            raise HTTPException(
                status_code=401,
                detail=f"{API_KEY_HEADER} header required",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    @app.get(
        "/v1/problems",
        response_model=ProblemsResponse,
        tags=["problems"],
        summary="Ranked, evidence-backed problems people report",
        description=(
            "Problems clustered from discussions (Hacker News, GitHub issues, Lobsters, Stack Exchange), "
            "ranked by demand. With `topic`, problems are retrieved by hybrid search over their evidence, "
            "filtered to relevance >= 0.5 and ranked by relevance x sqrt(demand). "
            "Responses are compact for agent tool use."
        ),
    )
    async def problems(
        st: StateDep,
        principal: ProtectedDep,
        response: Response,
        topic: Annotated[str | None, Query(min_length=2, max_length=256)] = None,
        category: ProblemCategory | None = None,
        since_days: Annotated[int, Query(ge=1, le=90)] = 30,
        min_voices: Annotated[int, Query(ge=1, le=100)] = 2,
        limit: Annotated[int, Query(ge=1, le=25)] = 10,
        evidence: Annotated[int, Query(ge=0, le=5, description="Evidence items per problem.")] = 3,
    ) -> ProblemsResponse:
        _require_key(st, principal)

        async def compute() -> tuple[ProblemsResponse, bool]:
            degraded: list[str] = []
            embedding: list[float] | None = None
            if topic and st.embedder is not None:
                try:
                    embedding = await asyncio.to_thread(st.embedder.embed_query, topic)
                except Exception:
                    log.exception("topic embedding failed; lexical-only problem retrieval")
                    degraded.append("dense_unavailable")
            now = datetime.now(UTC)
            async with st.sessionmaker() as session, session.begin():
                results = await find_problems(
                    session,
                    as_of=now,
                    topic=topic,
                    embedding=embedding,
                    category=category,
                    since_days=since_days,
                    min_voices=min_voices,
                    limit=limit,
                    evidence_limit=evidence,
                )
            body = ProblemsResponse(as_of=now, ranker=RANKER, degraded=degraded, results=results)
            return body, not degraded  # a degraded answer is served, never cached

        params = {
            # Exact string: the embedding sees it verbatim, so case or spacing can change ranking.
            "topic": topic,
            "category": category,
            "since_days": since_days,
            "min_voices": min_voices,
            "limit": limit,
            "evidence": evidence,
        }
        body, status = await st.cache.get_or_compute("problems", params, ProblemsResponse, compute)
        for reason in body.degraded:
            _mark_degraded(response, reason)
        response.headers["X-XM-Cache"] = status
        response.headers["Cache-Control"] = "private, max-age=60"
        return body

    @app.get(
        "/v1/problems/{problem_id}",
        response_model=ProblemDetail,
        tags=["problems"],
        summary="One problem with full evidence and demand factors",
        responses={404: {"description": "Problem not found"}},
    )
    async def problem(
        st: StateDep,
        principal: ProtectedDep,
        response: Response,
        problem_id: Annotated[int, PathParam(ge=1)],
        evidence: Annotated[int, Query(ge=1, le=25)] = 10,
    ) -> ProblemDetail:
        _require_key(st, principal)
        async with st.sessionmaker() as session:
            found = await get_problem(session, problem_id, as_of=datetime.now(UTC), evidence_limit=evidence)
        if found is None:
            raise HTTPException(status_code=404, detail="problem not found")
        response.headers["Cache-Control"] = "private, max-age=60"
        return found

    return app
