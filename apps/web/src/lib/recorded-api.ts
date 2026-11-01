/** Pure recorded-edition adapter. No credentials, embedding model or network access. */
import source from "../data/demo-snapshot.json" with { type: "json" };
import type {
  ApiResult,
  FeedResponse,
  MapResponse,
  ProblemDetail,
  PulseResponse,
  Stats,
  StoryDetail,
  StorySummary,
} from "./api";
import type { Weights } from "./ranking";

type Params = Record<string, string | number | undefined | null>;
export interface DemoSnapshot {
  version: number;
  captured_at: string;
  scope: string;
  embedding_model: string;
  search_mode: string;
  labels: string;
  coverage: {
    exported_stories: number;
    corpus_stories: number;
    exported_problems: number;
    feed_window_hours: number;
  };
  stats: Stats;
  feed: FeedResponse & { weights: Weights };
  stories: StoryDetail[];
  problems: ProblemDetail[];
  map: MapResponse;
  pulse: PulseResponse;
}
export const snapshot = source as unknown as DemoSnapshot;
const defaults = snapshot.feed.weights;
const words = (text: string) =>
  text
    .normalize("NFKD")
    .toLowerCase()
    .match(/[\p{L}\p{N}]+/gu) ?? [];
const tokens = (text: string) =>
  [...new Set(words(text.slice(0, 256)))].slice(0, 16);
function matches(text: string, query: string): boolean {
  const haystack = new Set(words(text));
  return tokens(query).every((t) => haystack.has(t));
}
function number(
  params: Params,
  key: string,
  fallback: number,
  min: number,
  max: number,
) {
  const raw = params[key];
  const value =
    raw === undefined || raw === null || raw === "" ? fallback : Number(raw);
  return Number.isFinite(value)
    ? Math.min(max, Math.max(min, value))
    : fallback;
}
export function recordedFeed(params: Params): FeedResponse {
  const w: Weights = {
    sources: number(params, "w_sources", defaults.sources, 0, 3),
    authority: number(params, "w_authority", defaults.authority, 0, 3),
    hn_points: number(params, "w_points", defaults.hn_points, 0, 1.5),
    half_life_hours: number(
      params,
      "half_life_hours",
      defaults.half_life_hours,
      2,
      168,
    ),
  };
  const standard = Object.keys(defaults).every(
    (key) => w[key as keyof Weights] === defaults[key as keyof Weights],
  );
  const hours = number(params, "window_hours", 72, 1, 336);
  const cutoff = Date.parse(snapshot.captured_at) - hours * 3600000;
  const result: StorySummary[] = snapshot.feed.results
    .filter((story) => {
      const detail = snapshot.stories.find((d) => d.story.id === story.id);
      return detail?.articles.some(
        (a) => Date.parse(a.published_at ?? a.discovered_at) >= cutoff,
      );
    })
    .map((story) => {
      const s = story.signals!;
      const signals = {
        coverage: w.sources * Math.log1p(story.source_count),
        authority: w.authority * (s.authority / defaults.authority),
        community: w.hn_points * Math.log1p(s.hn_points),
        freshness: 0.5 ** (s.hours_since_published / w.half_life_hours),
        hn_points: s.hn_points,
        hours_since_published: s.hours_since_published,
      };
      return {
        ...story,
        score: standard
          ? story.score
          : (signals.coverage + signals.authority + signals.community) *
            signals.freshness,
        signals: standard ? s : signals,
      };
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || a.id - b.id);
  const remaining = [...result],
    head: StorySummary[] = [],
    counts = new Map<string, number>();
  while (remaining.length && head.length < 20) {
    const cap = head.length < 10 ? 2 : 3;
    let index = remaining.findIndex(
      (s) => (counts.get(s.sources[0] ?? "") ?? 0) < cap,
    );
    if (index < 0) index = 0;
    const [item] = remaining.splice(index, 1);
    head.push(item);
    counts.set(
      item.sources[0] ?? "",
      (counts.get(item.sources[0] ?? "") ?? 0) + 1,
    );
  }
  return {
    ranker: "recorded-heuristic-v1",
    weights: w,
    results: [...head, ...remaining].slice(
      0,
      number(params, "limit", 30, 1, 50),
    ),
  };
}
export function recordedResult(
  path: string,
  params: Params = {},
): ApiResult<unknown> {
  const start = performance.now();
  let data: unknown = null;
  const statusForMissing = 404;
  if (path === "/v1/stats") data = snapshot.stats;
  else if (path === "/v1/feed") data = recordedFeed(params);
  else if (path === "/v1/map") data = snapshot.map;
  else if (path === "/v1/pulse") data = snapshot.pulse;
  else if (path === "/v1/search") {
    const query = String(params.q ?? "").slice(0, 256);
    const rows = tokens(query).length
      ? snapshot.stories.filter((d) =>
          matches(
            d.story.title + " " + d.articles.map((a) => a.title).join(" "),
            query,
          ),
        )
      : [];
    data = {
      query,
      results: rows
        .slice(0, number(params, "limit", 15, 1, 50))
        .map((d) => ({ ...d.story, score: null })),
      degraded: ["recorded_snapshot", "keyword_only"],
    };
  } else if (path === "/v1/problems") {
    const topic = String(params.topic ?? "");
    const category = params.category;
    const filtered = snapshot.problems.filter(
      (p) =>
        p.voice_count >= number(params, "min_voices", 2, 1, 100) &&
        (!category || p.category === category) &&
        (!topic ||
          matches(
            [
              p.statement,
              ...p.evidence.map((e) => e.excerpt),
              ...p.entities,
            ].join(" "),
            topic,
          )),
    );
    data = {
      as_of: snapshot.captured_at,
      ranker: "recorded-demand-v0",
      degraded: ["recorded_snapshot", ...(topic ? ["keyword_only"] : [])],
      results: filtered
        .slice(0, number(params, "limit", 10, 1, 25))
        .map((p) => ({
          ...p,
          evidence: p.evidence.slice(0, number(params, "evidence", 2, 0, 5)),
        })),
    };
  } else {
    const story = path.match(/^\/v1\/stories\/(\d+)$/);
    const problem = path.match(/^\/v1\/problems\/(\d+)$/);
    if (story)
      data =
        snapshot.stories.find((s) => s.story.id === Number(story[1])) ?? null;
    if (problem)
      data = snapshot.problems.find((p) => p.id === Number(problem[1])) ?? null;
  }
  return {
    data: structuredClone(data),
    status: data === null ? statusForMissing : 200,
    timing: null,
    degraded: "recorded_snapshot",
    cache: "recorded",
    elapsedMs: performance.now() - start,
  };
}
