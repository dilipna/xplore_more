import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Eyebrow, Metric, SourceBadge, Unavailable } from "@/components/ui";
import { type ArticleOut, getStory } from "@/lib/api";
import { relativeTime, shortDate } from "@/lib/format";

/** When a source reported: the publisher's own date, else when we first saw it. */
function reportedAt(a: ArticleOut): { ms: number; dated: boolean } {
  return { ms: new Date(a.published_at ?? a.discovered_at).getTime(), dated: a.published_at !== null };
}

function gap(ms: number): string {
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `${minutes} min later`;
  const hours = minutes / 60;
  if (hours < 48) return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)} h later`;
  return `${Math.round(hours / 24)} days later`;
}

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Story" };

export default async function StoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const storyId = Number(id);
  if (!Number.isInteger(storyId) || storyId < 1) notFound();
  const result = await getStory(storyId);
  if (result.status === 404) notFound();
  const d = result.data;
  // Earliest report first; ties keep the API's order (highest authority first).
  const ordered = d ? [...d.articles].sort((a, b) => reportedAt(a).ms - reportedAt(b).ms) : [];
  const race = new Set(ordered.map((a) => a.source_id)).size > 1;
  const first = ordered[0];
  const firstMs = first ? reportedAt(first).ms : 0;

  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <Link href="/" className="text-sm text-fg-500 hover:text-signal-300">
        ← News
      </Link>
      {!d ? (
        <div className="mt-8">
          <Unavailable what="this story" />
        </div>
      ) : (
        <>
          <h1 className="mt-6 text-pretty text-2xl leading-snug font-semibold tracking-tight [overflow-wrap:anywhere] md:text-3xl">
            {d.story.title}
          </h1>
          <div className="mt-8 grid grid-cols-3 gap-6">
            <Metric value={d.story.source_count} label="sources" />
            <Metric value={d.story.article_count} label="articles" />
            <Metric value={relativeTime(d.story.first_seen_at)} label="first seen" />
          </div>
          <section className="mt-12">
            <Eyebrow>{race ? "Race to report" : "Coverage"}</Eyebrow>
            <p className="mt-3 text-sm leading-relaxed text-fg-400">
              {race
                ? `${first!.source_name} reported first. Times are each publisher's own date where the feed gives one, otherwise when XploreMore first saw the article.`
                : "Articles are grouped automatically when their text, meaning, names and timing line up."}
            </p>
            <ol className="mt-6 flex flex-col gap-3">
              {ordered.map((a, i) => {
                const t = reportedAt(a);
                return (
                  <li key={a.id} className="panel flex items-start justify-between gap-4 p-4">
                    <div className="min-w-0">
                      <a
                        href={a.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[15px] text-fg-50 [overflow-wrap:anywhere] hover:text-signal-300"
                      >
                        {a.title}
                      </a>
                      <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-fg-500">
                        <SourceBadge id={a.source_id} />
                        <span>{a.source_name}</span>
                        <span>
                          · {shortDate(a.published_at ?? a.discovered_at)}
                          {!t.dated && " (first seen)"}
                        </span>
                      </p>
                    </div>
                    {race && (
                      <span
                        className={`shrink-0 font-mono text-[11px] ${i === 0 ? "text-signal-400" : "text-fg-500"}`}
                      >
                        {i === 0 ? "First" : gap(t.ms - firstMs)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
