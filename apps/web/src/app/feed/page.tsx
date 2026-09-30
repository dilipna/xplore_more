import type { Metadata } from "next";
import Link from "next/link";
import { FeedPulse } from "@/components/feed-pulse";
import { AutoRefresh } from "@/components/live";
import { RankingPanel } from "@/components/ranking-panel";
import { RightRail } from "@/components/right-rail";
import { Shell } from "@/components/shell";
import { StoryCard } from "@/components/story-card";
import { Unavailable } from "@/components/ui";
import { getFeed } from "@/lib/api";
import { DEFAULT_WEIGHTS, parseWeights, weightParams } from "@/lib/ranking";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "All stories" };

const WINDOWS = [
  { hours: 24, label: "Today" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "This week" },
];
const LIMIT = 40;

export default async function FeedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const window = typeof params.window === "string" ? params.window : undefined;
  const hours = WINDOWS.some((w) => String(w.hours) === window) ? Number(window) : 72;
  const weights = parseWeights(params);
  // With custom weights, also fetch the default order (cached by the API) to show rank changes.
  const [result, standard] = await Promise.all([
    getFeed(hours, LIMIT, weights),
    weights ? getFeed(hours, LIMIT) : Promise.resolve(null),
  ]);
  const stories = result.data?.results ?? [];
  const defaultRank = new Map((standard?.data?.results ?? []).map((s, i) => [s.id, i + 1]));
  const tuned = new URLSearchParams(weightParams(weights)).toString();

  return (
    <Shell rail={<RightRail />}>
      <AutoRefresh seconds={60} />
      <FeedPulse ids={stories.map((s) => s.id)} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-xl font-bold tracking-tight">All stories</h1>
        {WINDOWS.map((w) => (
          <Link
            key={w.hours}
            href={`/feed?window=${w.hours}${tuned ? `&${tuned}` : ""}`}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${
              hours === w.hours ? "bg-signal-400 text-black" : "text-fg-400 hover:bg-field-850 hover:text-fg-50"
            }`}
          >
            {w.label}
          </Link>
        ))}
      </div>
      <RankingPanel weights={weights ?? DEFAULT_WEIGHTS} />
      {!result.data ? (
        <Unavailable what="stories" />
      ) : stories.length === 0 ? (
        <p className="text-fg-400">Nothing yet in this window. Try a longer one.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {stories.map((s, i) => {
            const was = defaultRank.get(s.id);
            const delta = !weights || !standard?.data ? undefined : was === undefined ? "new" : was - (i + 1);
            return <StoryCard key={s.id} story={s} rank={i + 1} why delta={delta} />;
          })}
        </div>
      )}
    </Shell>
  );
}
