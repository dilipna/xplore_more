import { headers } from "next/headers";
import type { StorySummary } from "./api";
import { sourceName } from "./sources";

export const SITE_NAME = "XploreMore";

/** Absolute origin for feeds, the sitemap and share cards: XM_SITE_URL, else the request's host. */
export async function siteOrigin(): Promise<string> {
  const configured = process.env.XM_SITE_URL;
  if (configured) return configured.replace(/\/$/, "");
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3100";
  const local = /^(localhost|127\.|\[::1\])/.test(host);
  const proto = h.get("x-forwarded-proto") ?? (local ? "http" : "https");
  return `${proto}://${host}`;
}

export function escapeXml(s: string): string {
  return s.replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[c]!);
}

export interface FeedItem {
  title: string;
  link: string;
  guid: string;
  date: string;
  description: string;
}

/** RSS 2.0, the format every reader supports. Descriptions are plain text, never generated prose. */
export function rss(channel: { title: string; link: string; self: string; description: string }, items: FeedItem[]) {
  const body = items
    .map(
      (i) => `    <item>
      <title>${escapeXml(i.title)}</title>
      <link>${escapeXml(i.link)}</link>
      <guid isPermaLink="false">${escapeXml(i.guid)}</guid>
      <pubDate>${new Date(i.date).toUTCString()}</pubDate>
      <description>${escapeXml(i.description)}</description>
    </item>`,
    )
    .join("\n");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${escapeXml(channel.title)}</title>
    <link>${escapeXml(channel.link)}</link>
    <atom:link href="${escapeXml(channel.self)}" rel="self" type="application/rss+xml"/>
    <description>${escapeXml(channel.description)}</description>
    <language>en</language>
${body}
  </channel>
</rss>
`;
  return new Response(xml, {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=300" },
  });
}

export function storyItem(origin: string, s: StorySummary): FeedItem {
  const others = s.sources.length - 1;
  return {
    title: s.title,
    link: `${origin}/stories/${s.id}`,
    guid: `xploremore-story-${s.id}`,
    date: s.published_at ?? s.first_seen_at,
    description: `${sourceName(s.sources[0] ?? "")}${others > 0 ? ` and ${others} more` : ""}. Original: ${s.url}`,
  };
}

