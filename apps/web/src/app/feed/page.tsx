import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/live";
import { StoryRow } from "@/components/story-row";
import { TopStories } from "@/components/top-stories";
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
        <div className="mt-8 flex flex-wrap items-center gap-2 text-sm">
          {WINDOWS.map((w) => (
            <Link
              key={w.hours}
              href={`/feed?window=${w.hours}`}
              className={`rounded-lg px-3 py-1.5 ${hours === w.hours ? "bg-signal-400/10 text-signal-400 shadow-[inset_0_0_0_1px_rgb(57_255_127/0.35)]" : "text-fg-400 hover:text-signal-300"}`}
            >
              {w.label}
            </Link>
          ))}
          <span className="ml-auto font-mono text-xs text-fg-500">
            <AutoRefresh seconds={60} />
          </span>
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
            <TopStories stories={stories.slice(0, 6)} windowLabel={WINDOWS.find((w) => w.hours === hours)?.label ?? ""} />
            {stories.length > 6 && (
              <ol className="mt-6 flex flex-col gap-3">
                {stories.slice(6).map((s, i) => (
                  <StoryRow key={s.id} story={s} rank={i + 7} />
                ))}
              </ol>
            )}
          </>
        )}
      </section>
    </>
  );
}
