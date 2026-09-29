import type { Metadata } from "next";
import Link from "next/link";
import { FeedPulse } from "@/components/feed-pulse";
import { AutoRefresh } from "@/components/live";
import { RightRail } from "@/components/right-rail";
import { Shell } from "@/components/shell";
import { StoryCard } from "@/components/story-card";
import { Unavailable } from "@/components/ui";
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
    <Shell rail={<RightRail />}>
      <AutoRefresh seconds={60} />
      <FeedPulse ids={stories.map((s) => s.id)} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-xl font-bold tracking-tight">All stories</h1>
        {WINDOWS.map((w) => (
          <Link
            key={w.hours}
            href={`/feed?window=${w.hours}`}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${
              hours === w.hours ? "bg-signal-400 text-black" : "text-fg-400 hover:bg-field-850 hover:text-fg-50"
            }`}
          >
            {w.label}
          </Link>
        ))}
      </div>
      {!result.data ? (
        <Unavailable what="stories" />
      ) : stories.length === 0 ? (
        <p className="text-fg-400">Nothing yet in this window. Try a longer one.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {stories.map((s, i) => (
            <StoryCard key={s.id} story={s} rank={i + 1} />
          ))}
        </div>
      )}
    </Shell>
  );
}
