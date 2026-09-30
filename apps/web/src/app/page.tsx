import Link from "next/link";
import { redirect } from "next/navigation";
import { FeedPulse } from "@/components/feed-pulse";
import { AutoRefresh } from "@/components/live";
import { ProblemCard } from "@/components/problem-card";
import { RightRail } from "@/components/right-rail";
import { Shell } from "@/components/shell";
import { StoryCard } from "@/components/story-card";
import { Unavailable } from "@/components/ui";
import { getProblems, getTopStories, type ProblemSummary, type StorySummary } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ topic?: string; category?: string; voices?: string; sort?: string }>;

type Item = { kind: "story"; story: StorySummary; rank: number } | { kind: "problem"; problem: ProblemSummary };

export default async function HomePage({ searchParams }: { searchParams: SearchParams }) {
  // The problem list used to live here; keep old filter links working.
  const sp = await searchParams;
  if (sp.topic || sp.category || sp.voices) {
    const q = new URLSearchParams(
      Object.entries({ topic: sp.topic, category: sp.category, voices: sp.voices }).filter(([, v]) => v) as [string, string][],
    );
    redirect(`/problems?${q}`);
  }
  const sort = sp.sort === "new" ? "new" : "top";

  const [top, problems] = await Promise.all([getTopStories(), getProblems({ min_voices: 2, limit: 9 })]);
  let stories = top.data?.results ?? [];
  if (sort === "new") {
    const time = (s: StorySummary) => new Date(s.published_at ?? s.first_seen_at).getTime();
    stories = [...stories].sort((a, b) => time(b) - time(a));
  }
  // The rail shows the top 5 problems; the feed mixes in the next ones, one every 4 stories.
  const extra = problems.data?.results.slice(5) ?? [];
  const items: Item[] = [];
  stories.forEach((story, i) => {
    items.push({ kind: "story", story, rank: i + 1 });
    if ((i + 1) % 4 === 0 && extra.length) items.push({ kind: "problem", problem: extra.shift()! });
  });

  const tab = (on: boolean) =>
    `rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
      on ? "bg-signal-400 text-black" : "text-fg-400 hover:bg-field-850 hover:text-fg-50"
    }`;

  return (
    <Shell rail={<RightRail />}>
      <AutoRefresh seconds={60} />
      <FeedPulse ids={stories.map((s) => s.id)} />
      <div className="mb-4 flex items-center gap-2">
        <Link href="/" className={tab(sort === "top")}>
          Top
        </Link>
        <Link href="/?sort=new" className={tab(sort === "new")}>
          New
        </Link>
        <span className="ml-auto text-xs text-fg-500">
          {stories.length} stories · last {top.windowHours === 72 ? "3 days" : "24 hours"}
        </span>
        <Link href="/feed" className="text-xs font-semibold text-signal-400 hover:text-signal-300 hover:underline">
          Tune the ranking
        </Link>
        <Link href="/briefing" className="text-xs font-semibold text-signal-400 hover:text-signal-300 hover:underline">
          Daily briefing
        </Link>
      </div>

      {!top.data ? (
        <Unavailable what="the news" />
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((it) =>
            it.kind === "story" ? (
              <StoryCard
                key={`s${it.story.id}`}
                story={it.story}
                rank={it.rank}
                lead={sort === "top" && it.rank === 1}
              />
            ) : (
              <ProblemCard key={`p${it.problem.id}`} problem={it.problem} compactLabel="Problem people are reporting" />
            ),
          )}
          <Link
            href="/feed?window=168"
            className="panel panel-hover block p-4 text-center text-sm font-semibold text-signal-400"
          >
            More stories from this week
          </Link>
        </div>
      )}
    </Shell>
  );
}
