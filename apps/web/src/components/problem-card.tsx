import Link from "next/link";
import type { ProblemSummary } from "@/lib/api";
import { categoryLabel, displayStatement, echoesStatement, formatCount, platformInfo, relativeTime } from "@/lib/format";
import { ArrowUpIcon, ChatIcon, UsersIcon } from "./icons";

/** A problem as a forum post. The left column is the number of distinct people who reported it. */
export function ProblemCard({ problem, compactLabel }: { problem: ProblemSummary; compactLabel?: string }) {
  const statement = displayStatement(
    problem.statement,
    problem.evidence.map((e) => e.excerpt),
  );
  const quote = problem.evidence.find((e) => !echoesStatement(problem.statement, e.excerpt));
  // Engagement of the most-discussed post shown (the list endpoint returns a few posts per problem).
  const top = [...problem.evidence].sort(
    (a, b) => (b.engagement.points ?? 0) + (b.engagement.comments ?? 0) - ((a.engagement.points ?? 0) + (a.engagement.comments ?? 0)),
  )[0];
  const platform = platformInfo(problem.platforms[0] ?? "");

  return (
    <article className="panel panel-hover group relative flex overflow-hidden">
      <div className="flex w-14 shrink-0 flex-col items-center gap-0.5 bg-field-850/60 pt-4 text-signal-400" title="People who reported this">
        <ArrowUpIcon className="h-4 w-4" />
        <span className="font-mono text-base font-semibold tabular-nums">{problem.voice_count}</span>
        <span className="text-[10px] text-fg-500">{problem.voice_count === 1 ? "person" : "people"}</span>
      </div>

      <div className="min-w-0 flex-1 p-4">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-500">
          {compactLabel && <span className="font-semibold text-signal-400">{compactLabel}</span>}
          <span className="inline-flex items-center gap-1.5 font-semibold text-fg-200">
            <span className="h-2 w-2 rounded-full" style={{ background: platform.color }} aria-hidden="true" />
            {problem.platforms.map((p) => platformInfo(p).label).join(" + ")}
          </span>
          <span aria-hidden="true">·</span>
          <span>{relativeTime(problem.last_seen)}</span>
          <span className="rounded-full border border-amber-400/25 bg-amber-400/8 px-2 py-px text-[11px] text-amber-300">
            {categoryLabel(problem.category)}
          </span>
        </p>

        <h3 className="mt-2 line-clamp-3 text-pretty text-[16px] leading-snug font-semibold text-fg-50 [overflow-wrap:anywhere] group-hover:text-signal-300">
          <Link href={`/problems/${problem.id}`} className="after:absolute after:inset-0">
            {statement}
          </Link>
        </h3>

        {quote && (
          <p className="mt-2 line-clamp-2 border-l-2 border-signal-700 pl-3 text-sm leading-relaxed text-fg-400 [overflow-wrap:anywhere]">
            {quote.excerpt}
          </p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-fg-400">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-field-800 px-2.5 py-1">
            <UsersIcon className="h-3.5 w-3.5" />
            {problem.source_count === 1 ? "1 source" : `${problem.source_count} sources`}
          </span>
          {top && (top.engagement.points || top.engagement.comments) ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-field-800 px-2.5 py-1" title="On the most-discussed post">
              <ChatIcon className="h-3.5 w-3.5" />
              {[
                top.engagement.points ? `${formatCount(top.engagement.points)} points` : null,
                top.engagement.comments ? `${formatCount(top.engagement.comments)} replies` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          ) : null}
          <span className="ml-auto font-mono text-signal-300" title="Demand score">
            demand {problem.demand_score.toFixed(2)}
          </span>
        </div>
      </div>
    </article>
  );
}
