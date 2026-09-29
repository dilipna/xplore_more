import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/live";
import { StoryRow } from "@/components/story-row";
import { PageIntro, Unavailable } from "@/components/ui";
import { getFeed } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "All stories" };

const WINDOWS = [
  { hours: 24, label: "Today" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "This week" },
];

export default async function FeedPage({ searchParams }: { searchParams: Promise<{ window?: string }> }) {
  const { window } = await searchParams;
  const hours = WINDOWS.some((w) => String(w.hours) === window) ? Number(window) : 72;
  const result = await getFeed(hours, 40);
  const stories = result.data?.results ?? [];

  return (
    <>
      <AutoRefresh seconds={60} />
      <PageIntro title="All stories">
        <p className="mt-3 max-w-2xl text-fg-400">
          43 sources, from AI labs and engineering blogs to Hacker News, arXiv and GitHub releases. When several outlets
          cover the same thing, it shows up once.
        </p>
        <div className="mt-5 flex gap-1 text-sm">
          {WINDOWS.map((w) => (
            <Link
              key={w.hours}
              href={`/feed?window=${w.hours}`}
              className={`rounded-full px-3 py-1 ${hours === w.hours ? "bg-signal-400/10 text-signal-400" : "text-fg-400 hover:text-signal-300"}`}
            >
              {w.label}
            </Link>
          ))}
        </div>
      </PageIntro>
      <section className="mx-auto max-w-4xl px-5 pt-2 pb-12">
        {!result.data ? (
          <div className="mt-6">
            <Unavailable what="stories" />
          </div>
        ) : stories.length === 0 ? (
          <p className="mt-6 text-fg-400">Nothing yet in this window. Try a longer one.</p>
        ) : (
          <ol>
            {stories.map((s, i) => (
              <StoryRow key={s.id} story={s} rank={i + 1} />
            ))}
          </ol>
        )}
      </section>
    </>
  );
}
