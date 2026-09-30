// RSS for the most reported problems, optionally one category (?category=bug_or_reliability).
import { getProblems } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import { rss, SITE_NAME, siteOrigin } from "@/lib/site";

export const dynamic = "force-dynamic";

const CATEGORIES = new Set(["bug_or_reliability", "cost_or_performance", "missing_capability", "workflow_friction"]);

export async function GET(request: Request) {
  const origin = await siteOrigin();
  const raw = new URL(request.url).searchParams.get("category") ?? "";
  const category = CATEGORIES.has(raw) ? raw : undefined;
  const result = await getProblems({ category, min_voices: 2, limit: 25 });
  if (!result.data) return new Response("upstream unavailable", { status: 503 });
  const label = category ? categoryLabel(category as Parameters<typeof categoryLabel>[0]) : null;
  return rss(
    {
      title: label ? `${SITE_NAME}: problems, ${label}` : `${SITE_NAME}: most reported problems`,
      link: `${origin}/problems${category ? `?category=${category}` : ""}`,
      self: `${origin}/problems.xml${category ? `?category=${category}` : ""}`,
      description: "Problems several people report on Hacker News, GitHub, Lobsters and Stack Exchange, ranked by demand.",
    },
    result.data.results.map((p) => ({
      title: p.statement,
      link: `${origin}/problems/${p.id}`,
      guid: `xploremore-problem-${p.id}`,
      date: p.last_seen,
      description: `${p.voice_count} people on ${p.platforms.join(", ")}. ${categoryLabel(p.category)}. Demand ${p.demand_score.toFixed(2)}.`,
    })),
  );
}
