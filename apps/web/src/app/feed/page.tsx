import type { Metadata } from "next";
import Link from "next/link";
import { StoryRow } from "@/components/story-row";
import { PageIntro, Unavailable } from "@/components/ui";
import { getFeed } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Feed" };

const WINDOWS = [
  { hours: 24, label: "24 hours" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "7 days" },
];

export default async function FeedPage({ searchParams }: { searchParams: Promise<{ window?: string }> }) {
  const { window } = await searchParams;
  const hours = WINDOWS.some((w) => String(w.hours) === window) ? Number(window) : 72;
  const result = await getFeed(hours);
  const stories = result.data?.results ?? [];

  return (
    <>
      <PageIntro eyebrow="Ranked feed" title="What happened in tech, deduplicated.">
        <p className="mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-fg-400">
          43 sources — labs, engineering blogs, Hacker News, arXiv, GitHub releases — collapsed into stories and ranked
          by a transparent importance heuristic: coverage across sources, authority, engagement and freshness.
        </p>
        <div className="mt-8 flex flex-wrap gap-2 text-sm">
          {WINDOWS.map((w) => (
            <Link
              key={w.hours}
              href={`/feed?window=${w.hours}`}
              className={`rounded-lg px-3 py-1.5 ${hours === w.hours ? "bg-field-800 text-fg-50" : "text-fg-400 hover:text-fg-50"}`}
            >
              {w.label}
            </Link>
          ))}
        </div>
      </PageIntro>
      <section className="mx-auto max-w-6xl px-5 py-10">
        {!result.data ? (
          <Unavailable what="the feed" />
        ) : stories.length === 0 ? (
          <p className="text-fg-400">No stories in this window yet — try a longer one.</p>
        ) : (
          <>
            <p className="mb-4 font-mono text-[11px] text-fg-600">
              ranker {result.data.ranker} · {Math.round(result.elapsedMs)} ms
              {result.cache ? ` · cache ${result.cache}` : ""}
            </p>
            <ol className="flex flex-col gap-3">
              {stories.map((s, i) => (
                <StoryRow key={s.id} story={s} rank={i + 1} />
              ))}
            </ol>
          </>
        )}
      </section>
    </>
  );
}
