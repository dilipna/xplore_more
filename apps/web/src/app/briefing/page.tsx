import type { Metadata } from "next";
import Link from "next/link";
import { PrintButton } from "@/components/print-button";
import { PlatformBadge, SourceBadge, Unavailable } from "@/components/ui";
import { type ArticleOut, getProblems, getStory, getTopStories } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import { sourceName } from "@/lib/sources";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Daily briefing",
  description: "The top stories and the most reported problems, picked by an explainable ranking. No AI-written text.",
};

const STORIES = 5;
const PROBLEMS = 3;

function firstReport(articles: ArticleOut[]) {
  const when = (a: ArticleOut) => new Date(a.published_at ?? a.discovered_at).getTime();
  const sorted = [...articles].sort((a, b) => when(a) - when(b));
  if (new Set(sorted.map((a) => a.source_id)).size < 2) return null;
  const hours = (when(sorted[sorted.length - 1]) - when(sorted[0])) / 3.6e6;
  return { first: sorted[0].source_name, others: sorted.length - 1, hours };
}

export default async function BriefingPage() {
  const [top, problems] = await Promise.all([getTopStories(), getProblems({ min_voices: 2, limit: PROBLEMS })]);
  const stories = (top.data?.results ?? []).slice(0, STORIES);
  const details = await Promise.all(stories.map((s) => getStory(s.id)));
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  return (
    <div className="mx-auto max-w-3xl px-5 py-10 print:max-w-none print:px-0 print:py-0">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b hairline pb-5">
        <div>
          <p className="text-sm text-fg-500">{today}</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Daily briefing</h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-fg-400">
            The {STORIES} top stories of the last {top.windowHours === 72 ? "3 days (a quiet day: fewer than 8 stories in 24 hours)" : "24 hours"} and
            the {PROBLEMS} problems the most people are reporting. Everything here is picked by the same explainable ranking as the
            feed and quoted as published. Nothing is written by AI.
          </p>
        </div>
        <PrintButton />
      </header>

      <section className="mt-8" aria-labelledby="b-stories">
        <h2 id="b-stories" className="text-lg font-semibold text-fg-50">
          Top stories
        </h2>
        {!top.data ? (
          <div className="mt-4">
            <Unavailable what="the top stories" />
          </div>
        ) : (
          <ol className="mt-4 flex flex-col gap-5">
            {stories.map((s, i) => {
              const race = details[i].data ? firstReport(details[i].data!.articles) : null;
              const why = s.signals;
              return (
                <li key={s.id} className="flex gap-4 break-inside-avoid">
                  <span className="w-6 shrink-0 font-mono text-lg text-signal-400 print:text-black">{i + 1}</span>
                  <div className="min-w-0">
                    <Link
                      href={`/stories/${s.id}`}
                      className="text-[17px] leading-snug font-semibold text-fg-50 [overflow-wrap:anywhere] hover:text-signal-300"
                    >
                      {s.title}
                    </Link>
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-500">
                      <SourceBadge id={s.sources[0] ?? ""} />
                      <span>{sourceName(s.sources[0] ?? "")}</span>
                      {s.source_count > 1 && <span>· {s.source_count} sources</span>}
                      {race && (
                        <span>
                          · {race.first} reported first; {race.others} more within{" "}
                          {race.hours < 1 ? `${Math.max(1, Math.round(race.hours * 60))} min` : `${race.hours.toFixed(1)} h`}
                        </span>
                      )}
                    </p>
                    {why && (
                      <p className="mt-1 font-mono text-[11px] text-fg-600">
                        why here: coverage {why.coverage.toFixed(2)} + authority {why.authority.toFixed(2)} + community{" "}
                        {why.community.toFixed(2)} × freshness {why.freshness.toFixed(2)}
                      </p>
                    )}
                    <a href={s.url} className="mt-1 block truncate text-xs text-fg-500 hover:text-signal-300 print:whitespace-normal">
                      {s.url}
                    </a>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section className="mt-10 break-inside-avoid" aria-labelledby="b-problems">
        <h2 id="b-problems" className="text-lg font-semibold text-fg-50">
          Most reported problems
        </h2>
        {!problems.data ? (
          <div className="mt-4">
            <Unavailable what="problems" />
          </div>
        ) : (
          <ol className="mt-4 flex flex-col gap-5">
            {problems.data.results.map((p, i) => (
              <li key={p.id} className="flex gap-4 break-inside-avoid">
                <span className="w-6 shrink-0 font-mono text-lg text-signal-400 print:text-black">{i + 1}</span>
                <div className="min-w-0">
                  <Link
                    href={`/problems/${p.id}`}
                    className="text-[15px] leading-snug font-semibold text-fg-50 [overflow-wrap:anywhere] hover:text-signal-300"
                  >
                    {p.statement}
                  </Link>
                  <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-fg-500">
                    <span>
                      {p.voice_count} people · {categoryLabel(p.category)}
                    </span>
                    {p.platforms.map((pl) => (
                      <PlatformBadge key={pl} platform={pl} />
                    ))}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
