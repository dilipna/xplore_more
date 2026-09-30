// JSON Feed 1.1 (https://jsonfeed.org) for the top stories, or one topic with ?q=.
import { getTopStories, search } from "@/lib/api";
import { SITE_NAME, siteOrigin, storyItem } from "@/lib/site";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const origin = await siteOrigin();
  const q = new URL(request.url).searchParams.get("q")?.trim().slice(0, 64);
  const result = q ? await search(q, 20) : await getTopStories();
  if (!result.data) return Response.json({ error: "upstream unavailable" }, { status: 503 });
  const feed = {
    version: "https://jsonfeed.org/version/1.1",
    title: q ? `${SITE_NAME}: ${q}` : `${SITE_NAME}: top stories`,
    home_page_url: q ? `${origin}/search?q=${encodeURIComponent(q)}` : origin,
    feed_url: `${origin}/feed.json${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    language: "en",
    items: result.data.results.map((s) => {
      const i = storyItem(origin, s);
      return { id: i.guid, url: i.link, external_url: s.url, title: i.title, content_text: i.description, date_published: new Date(i.date).toISOString() };
    }),
  };
  return new Response(JSON.stringify(feed), {
    headers: { "Content-Type": "application/feed+json; charset=utf-8", "Cache-Control": "public, max-age=300" },
  });
}
