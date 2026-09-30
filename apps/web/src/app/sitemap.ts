import type { MetadataRoute } from "next";
import { getProblems, getTopStories } from "@/lib/api";
import { siteOrigin } from "@/lib/site";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const origin = await siteOrigin();
  const [top, problems] = await Promise.all([getTopStories(), getProblems({ min_voices: 2, limit: 25 })]);
  const pages = ["/", "/feed", "/problems", "/briefing", "/search", "/how-it-works"].map((p) => ({
    url: origin + p,
    changeFrequency: "hourly" as const,
  }));
  const stories = (top.data?.results ?? []).map((s) => ({
    url: `${origin}/stories/${s.id}`,
    lastModified: s.published_at ?? s.first_seen_at,
  }));
  const probs = (problems.data?.results ?? []).map((p) => ({ url: `${origin}/problems/${p.id}`, lastModified: p.last_seen }));
  return [...pages, ...stories, ...probs];
}
