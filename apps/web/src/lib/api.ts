/**
 * Server-side client for the XploreMore REST API.
 *
 * Every page renders on the server at request time (force-dynamic), so the API URL and key
 * never reach the browser, CORS never enters the picture, and a slow or down API degrades to
 * an explicit "unavailable" state instead of a broken page. Speed comes from the API's own
 * Redis response cache, not from caching here.
 */

import { cache } from "react";
import { type Weights, weightParams } from "./ranking";

export type ProblemCategory =
  | "bug_or_reliability"
  | "cost_or_performance"
  | "missing_capability"
  | "workflow_friction";

export interface Engagement {
  points: number | null;
  comments: number | null;
  reactions: number | null;
}

export interface Evidence {
  source_id: string;
  platform: string;
  url: string;
  excerpt: string;
  engagement: Engagement;
  date: string;
  p_problem: number | null;
}

export interface ProblemSummary {
  id: number;
  statement: string;
  category: ProblemCategory | null;
  demand_score: number;
  voice_count: number;
  source_count: number;
  platforms: string[];
  first_seen: string;
  last_seen: string;
  entities: string[];
  relevance: number | null;
  evidence: Evidence[];
}

export interface ProblemsResponse {
  as_of: string;
  ranker: string;
  degraded: string[];
  results: ProblemSummary[];
}

export interface DemandFactors {
  voices: number;
  sources: number;
  recency: number;
  engagement: number;
  category: number;
}

export interface ProblemDetail extends ProblemSummary {
  member_count: number;
  effective_voices: number;
  demand_factors: DemandFactors;
  scorer_version: string;
}

export interface StorySummary {
  id: number;
  title: string;
  url: string;
  source_count: number;
  article_count: number;
  sources: string[];
  first_seen_at: string;
  published_at: string | null;
  score: number | null;
  /** Feed only: the heuristic's parts, score = (coverage + authority + community) * freshness. */
  signals?: RankSignals | null;
}

export interface RankSignals {
  coverage: number;
  authority: number;
  community: number;
  freshness: number;
  hn_points: number;
  hours_since_published: number;
}

export interface SearchResponse {
  query: string;
  results: StorySummary[];
  degraded: string[];
}

export interface FeedResponse {
  ranker: string;
  weights?: Weights | null;
  results: StorySummary[];
}

export interface ArticleOut {
  id: string;
  title: string;
  url: string;
  source_id: string;
  source_name: string;
  published_at: string | null;
  discovered_at: string;
  content_origin: string;
}

export interface StoryDetail {
  story: StorySummary;
  articles: ArticleOut[];
}

export interface Stats {
  as_of: string;
  sources: number;
  articles: number;
  discussions: number;
  voices: number;
  platforms: string[];
  stories: number;
  multi_source_stories: number;
  problems: number;
  multi_voice_problems: number;
  last_indexed_at: string | null;
}

export interface ApiResult<T> {
  data: T | null;
  /** HTTP status, or 0 when the API could not be reached at all. */
  status: number;
  /** Raw Server-Timing header, when the endpoint sends one (search does). */
  timing: string | null;
  /** Comma-separated degradation reasons from X-XM-Degraded, if any. */
  degraded: string | null;
  cache: string | null;
  elapsedMs: number;
}

const API_URL = (process.env.XM_API_URL ?? "http://127.0.0.1:8765").replace(/\/$/, "");
const API_KEY = process.env.XM_API_KEY;
const TIMEOUT_MS = 12_000; // covers a Cloud Run cold start of the API; normal responses are far faster

export async function apiGet<T>(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
): Promise<ApiResult<T>> {
  const url = new URL(API_URL + path);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (API_KEY) headers["X-XM-Api-Key"] = API_KEY;
  const started = performance.now();
  try {
    const response = await fetch(url, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const elapsedMs = performance.now() - started;
    const meta = {
      status: response.status,
      timing: response.headers.get("server-timing"),
      degraded: response.headers.get("x-xm-degraded"),
      cache: response.headers.get("x-xm-cache"),
      elapsedMs,
    };
    if (!response.ok) return { data: null, ...meta };
    return { data: (await response.json()) as T, ...meta };
  } catch {
    return {
      data: null,
      status: 0,
      timing: null,
      degraded: null,
      cache: null,
      elapsedMs: performance.now() - started,
    };
  }
}

/** Deduplicated per request: the header and the page can both ask for stats in one render. */
export const getStats = cache(() => apiGet<Stats>("/v1/stats"));

export function getProblems(params: {
  topic?: string;
  category?: string;
  min_voices?: number;
  limit?: number;
}) {
  return apiGet<ProblemsResponse>("/v1/problems", { ...params, evidence: 2, since_days: 30 });
}

/** Deduplicated per request: the page and its share-card metadata both need it. */
export const getProblem = cache((id: number) => apiGet<ProblemDetail>(`/v1/problems/${id}`, { evidence: 10 }));

export function search(q: string, limit = 15) {
  return apiGet<SearchResponse>("/v1/search", { q, limit });
}

export function getFeed(windowHours: number, limit = 25, weights: Weights | null = null) {
  return apiGet<FeedResponse>("/v1/feed", { window_hours: windowHours, limit, ...weightParams(weights) });
}

/** The feed's top stories for the ticker and the home page: last 24 h, widened to 3 days when a
 *  quiet night leaves too few. Deduplicated per request, so both callers share one API call. */
export const getTopStories = cache(async () => {
  const day = await getFeed(24, 30);
  if (!day.data || day.data.results.length >= 8) return { ...day, windowHours: 24 };
  return { ...(await getFeed(72, 30)), windowHours: 72 };
});

/** Deduplicated per request: the page and its share-card metadata both need it. */
export const getStory = cache((id: number) => apiGet<StoryDetail>(`/v1/stories/${id}`));

/** Parse a Server-Timing header ("embed;dur=12.3, lexical;dur=4.1") into ordered stages. */
export function parseServerTiming(header: string | null): { name: string; ms: number }[] {
  if (!header) return [];
  return header
    .split(",")
    .map((part) => {
      const [name, ...attrs] = part.trim().split(";");
      const dur = attrs.find((a) => a.trim().startsWith("dur="));
      return { name: name.trim(), ms: dur ? Number(dur.trim().slice(4)) : NaN };
    })
    .filter((stage) => stage.name && Number.isFinite(stage.ms));
}
