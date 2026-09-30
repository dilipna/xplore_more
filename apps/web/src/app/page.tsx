import Link from "next/link";
import { redirect } from "next/navigation";
import { FeedPulse } from "@/components/feed-pulse";
import { MapHero } from "@/components/map-hero";
import { PulseChart } from "@/components/pulse-chart";
import { AutoRefresh } from "@/components/live";
import { ProblemCard } from "@/components/problem-card";
import { RightRail } from "@/components/right-rail";
import { Shell } from "@/components/shell";
import { StoryCard } from "@/components/story-card";
import { Unavailable } from "@/components/ui";
import { getProblems, getPulse, getStats, getTopStories, type ProblemSummary, type StorySummary } from "@/lib/api";
import { formatCount } from "@/lib/format";

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

  const [top, problems, pulse, stats] = await Promise.all([
    getTopStories(),
    getProblems({ min_voices: 2, limit: 9 }),
    getPulse(72),
    getStats(),
  ]);
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
      <section className="panel relative mb-5 overflow-hidden" aria-labelledby="hero-title">
        <div className="hero-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative grid gap-2 md:grid-cols-[1fr_1.05fr]">
          <div className="flex min-w-0 flex-col p-5 sm:p-6">
            <p className="font-mono text-[11px] font-semibold tracking-wider text-signal-400">LIVE · NO LLM IN THE LOOP</p>
            <h1 id="hero-title" className="mt-2 text-balance text-3xl leading-tight font-bold tracking-tight sm:text-[34px]">
              The AI news, <span className="neon-text text-signal-400">mapped by meaning</span>
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-fg-400">
              {stats.data
                ? `${formatCount(stats.data.articles)} articles from ${stats.data.sources} sources, merged into ${formatCount(stats.data.stories)} stories, next to ${formatCount(stats.data.problems)} problems engineers are reporting. `
                : ""}
              Every ranking shows its working, and you can change it.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/feed" className="rounded-full border border-signal-400/50 px-3.5 py-1.5 text-xs font-semibold text-signal-300 hover:bg-signal-400/10">
                Tune the ranking
              </Link>
              <Link href="/briefing" className="rounded-full border hairline px-3.5 py-1.5 text-xs font-semibold text-fg-200 hover:border-signal-400/50">
                Today&apos;s briefing
              </Link>
            </div>
            {pulse.data && (
              <div className="mt-auto pt-5">
                <PulseChart data={pulse.data} />
              </div>
            )}
          </div>
          <div className="relative min-w-0 border-t hairline md:border-t-0 md:border-l">
            <MapHero />
          </div>
        </div>
      </section>
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
