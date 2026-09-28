import Link from "next/link";
import type { ProblemSummary } from "@/lib/api";
import { displayStatement, echoesStatement, platformInfo, plural, relativeTime } from "@/lib/format";
import { CategoryBadge, Meter, PlatformBadge } from "./ui";

export function ProblemCard({
  problem,
  rank,
  maxDemand,
}: {
  problem: ProblemSummary;
  rank: number;
  maxDemand: number;
}) {
  // Prefer a different post than the one the statement came from: for a multi-voice problem
  // that shows a second person reporting it, which is the point of clustering.
  const quote = problem.evidence.find((e) => !echoesStatement(problem.statement, e.excerpt));
  const statement = displayStatement(
    problem.statement,
    problem.evidence.map((e) => e.excerpt),
  );
  return (
    <article className="panel panel-hover group relative p-5 md:p-6">
      <div className="flex gap-5">
        <span className="hidden w-8 shrink-0 pt-0.5 text-right font-mono text-sm text-fg-600 tabular-nums md:block">
          {String(rank).padStart(2, "0")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <CategoryBadge category={problem.category} />
            {problem.platforms.map((p) => (
              <PlatformBadge key={p} platform={p} />
            ))}
            {problem.relevance !== null && (
              <span className="font-mono text-[11px] text-signal-300">
                {Math.round(problem.relevance * 100)}% match
              </span>
            )}
          </div>

          <h3 className="mt-3 text-pretty text-[17px] leading-snug text-fg-50">
            <Link href={`/problems/${problem.id}`} className="after:absolute after:inset-0">
              {statement.length > 240 ? `${statement.slice(0, 239).trimEnd()}…` : statement}
            </Link>
          </h3>

          {quote && (
            <div className="mt-3 border-l-2 border-field-600 pl-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-fg-600">
                another voice · {platformInfo(quote.platform).label}
              </p>
              <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-fg-400">{quote.excerpt}</p>
            </div>
          )}

          <div className="mt-5 grid grid-cols-2 items-end gap-x-6 gap-y-3 md:grid-cols-[repeat(3,auto)_1fr]">
            <span className="font-mono text-sm text-fg-50 tabular-nums">
              {plural(problem.voice_count, "person", "people")}
            </span>
            <span className="font-mono text-sm text-fg-200 tabular-nums">{plural(problem.source_count, "source")}</span>
            <span className="font-mono text-xs text-fg-500">seen {relativeTime(problem.last_seen)}</span>
            <div className="col-span-2 flex items-center gap-3 md:col-span-1">
              <span className="font-mono text-[11px] text-fg-500">demand</span>
              <Meter value={maxDemand > 0 ? problem.demand_score / maxDemand : 0} label="demand relative to the top result" />
              <span className="font-mono text-xs text-signal-300 tabular-nums">{problem.demand_score.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
