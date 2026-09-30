// RSS for the top stories, or for one topic with ?q= (the same results as /search).
import { getTopStories, search } from "@/lib/api";
import { rss, SITE_NAME, siteOrigin, storyItem } from "@/lib/site";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const origin = await siteOrigin();
  const q = new URL(request.url).searchParams.get("q")?.trim().slice(0, 64);
  const result = q ? await search(q, 20) : await getTopStories();
  if (!result.data) return new Response("upstream unavailable", { status: 503 });
  return rss(
    {
      title: q ? `${SITE_NAME}: ${q}` : `${SITE_NAME}: top stories`,
      link: q ? `${origin}/search?q=${encodeURIComponent(q)}` : origin,
      self: `${origin}/rss.xml${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      description: q
        ? `Stories about ${q} from the ${SITE_NAME} sources.`
        : "Top AI and infrastructure stories, one per event, ranked by an explainable heuristic.",
    },
    result.data.results.map((s) => storyItem(origin, s)),
  );
}
