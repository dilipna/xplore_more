import { recordedMode } from "@/lib/web-mode";
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
import {
  getProblems,
  getPulse,
  getStats,
  getTopStories,
  type ProblemSummary,
  type StorySummary,
} from "@/lib/api";
import { formatCount } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  topic?: string;
  category?: string;
  voices?: string;
  sort?: string;
}>;

type Item =
  | { kind: "story"; story: StorySummary; rank: number }
  | { kind: "problem"; problem: ProblemSummary };

export default async function HomePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  // The problem list used to live here; keep old filter links working.
  const sp = await searchParams;
  if (sp.topic || sp.category || sp.voices) {
    const q = new URLSearchParams(
      Object.entries({
        topic: sp.topic,
        category: sp.category,
        voices: sp.voices,
      }).filter(([, v]) => v) as [string, string][],
    );
    redirect(`/problems?${q}`);
  }
  const sort = sp.sort === "new" ? "new" : "top";

  const [top, problems, pulse, stats] = await Promise.all([
    getTopStories(),
    getProblems({ min_voices: recordedMode() ? 1 : 2, limit: 9 }),
    getPulse(72),
    getStats(),
  ]);
  let stories = top.data?.results ?? [];
  if (sort === "new") {
    const time = (s: StorySummary) =>
      new Date(s.published_at ?? s.first_seen_at).getTime();
    stories = [...stories].sort((a, b) => time(b) - time(a));
  }
  // The rail shows the top 5 problems; the feed mixes in the next ones, one every 4 stories.
  const extra = problems.data?.results.slice(5) ?? [];
  const items: Item[] = [];
  stories.forEach((story, i) => {
    items.push({ kind: "story", story, rank: i + 1 });
    if ((i + 1) % 4 === 0 && extra.length)
      items.push({ kind: "problem", problem: extra.shift()! });
  });

  const tab = (on: boolean) =>
    `rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
      on
        ? "bg-signal-400 text-black"
        : "text-fg-400 hover:bg-field-850 hover:text-fg-50"
    }`;

  return (
    <>
      <section className="relative overflow-hidden border-b hairline">
        <div
          className="hero-grid pointer-events-none absolute inset-0 opacity-60"
          aria-hidden="true"
        />
        <div className="relative mx-auto grid max-w-7xl items-center gap-10 px-5 py-12 md:py-16 lg:grid-cols-[1.05fr_1fr]">
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal-300">
              Source-linked technology intelligence
            </p>
            <h1
              id="hero-title"
              className="mt-5 max-w-2xl text-[clamp(2.5rem,5.5vw,4.5rem)] font-semibold leading-[1.05] tracking-[-0.045em]"
            >
              Find the signal.
              <br />
              <span className="text-signal-300">Keep the evidence.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-fg-200">
              Explore technical stories and the problems engineers report. Open
              the original source, inspect why an item ranks, and turn a
              promising problem into a reviewable build brief.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="/problems"
                className="rounded-full bg-signal-400 px-5 py-3 text-sm font-semibold text-black transition-colors hover:bg-signal-300"
              >
                Explore reported problems →
              </Link>
              <Link
                href="/feed"
                className="rounded-full border border-signal-700 px-5 py-3 text-sm font-semibold text-fg-50 transition-colors hover:bg-field-800"
              >
                Tune the feed
              </Link>
            </div>
            <p className="mt-5 text-xs leading-relaxed text-fg-400">
              {recordedMode()
                ? "Recorded pipeline capture · original dates retained · no inference API calls"
                : "Connected local service · explainable ranking · no LLM in the serving path"}
            </p>
            {stats.data && (
              <dl className="mt-8 grid max-w-xl grid-cols-3 gap-5 border-t hairline pt-6">
                {[
                  [stats.data.articles, "news articles indexed"],
                  [stats.data.discussions, "public reports ingested"],
                  [stats.data.problems, "problem hypotheses"],
                ].map(([value, label]) => (
                  <div key={label}>
                    <dt className="text-[11px] leading-relaxed text-fg-400">
                      {label}
                    </dt>
                    <dd className="mt-2 font-mono text-2xl text-signal-300">
                      {formatCount(Number(value))}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          <div className="min-w-0 overflow-hidden rounded-2xl border border-signal-700/50 bg-field-900/95 shadow-[0_20px_80px_#03260f80]">
            <div className="flex items-center justify-between border-b hairline px-5 py-4 font-mono text-[10px] uppercase tracking-wider">
              <span className="text-signal-300">Signal map</span>
              <span className="text-fg-400">
                {recordedMode()
                  ? "Captured embeddings"
                  : "Embedding-derived layout"}
              </span>
            </div>
            <MapHero />
            <div className="border-t hairline px-5 py-4 text-xs leading-relaxed text-fg-400">
              Neighbouring dots have similar text embeddings. Inspect a source
              before treating a cluster as evidence of demand.
            </div>
            {pulse.data && (
              <div className="border-t hairline px-5 pb-5 pt-3">
                <PulseChart data={pulse.data} />
              </div>
            )}
          </div>
        </div>
      </section>
      <Shell rail={<RightRail />}>
        <AutoRefresh seconds={60} enabled={!recordedMode()} />
        <FeedPulse ids={stories.map((s) => s.id)} />
        <section className="panel mb-5 border-signal-700/40 p-5 sm:p-6">
          <p className="font-mono text-[10px] uppercase tracking-[.15em] text-signal-300">
            Evidence → scope → human review
          </p>
          <h2 className="mt-3 text-xl font-semibold tracking-tight">
            A reported problem. A bounded next step.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-fg-400">
            Keep the original report beside the target user, exclusions and
            acceptance criteria. Export a draft for ProToPro; approval remains a
            separate decision.
          </p>
          <Link
            href="/workbench"
            className="mt-4 inline-block text-sm font-semibold text-signal-300"
          >
            Open the evidence workbench →
          </Link>
        </section>
        <div className="mb-4 flex items-center gap-2">
          <Link href="/" className={tab(sort === "top")}>
            Top
          </Link>
          <Link href="/?sort=new" className={tab(sort === "new")}>
            New
          </Link>
          <span className="ml-auto text-xs text-fg-500">
            {stories.length} stories · last{" "}
            {top.windowHours === 72 ? "3 days" : "24 hours"}
          </span>
          <Link
            href="/feed"
            className="text-xs font-semibold text-signal-400 hover:text-signal-300 hover:underline"
          >
            Tune the ranking
          </Link>
          <Link
            href="/briefing"
            className="text-xs font-semibold text-signal-400 hover:text-signal-300 hover:underline"
          >
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
                <ProblemCard
                  key={`p${it.problem.id}`}
                  problem={it.problem}
                  compactLabel="Problem people are reporting"
                />
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
    </>
  );
}
