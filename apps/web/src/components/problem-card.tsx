import Link from "next/link";
import type { ProblemSummary } from "@/lib/api";
import { categoryLabel, displayStatement, platformInfo, plural, relativeTime } from "@/lib/format";

/** One problem as a compact row: statement, who reported it, where, and its demand score. */
export function ProblemCard({
  problem,
  rank,
  maxDemand,
}: {
  problem: ProblemSummary;
  rank: number;
  maxDemand: number;
}) {
  const statement = displayStatement(
    problem.statement,
    problem.evidence.map((e) => e.excerpt),
  );
  const width = maxDemand > 0 ? Math.max(4, (problem.demand_score / maxDemand) * 100) : 0;
  return (
    <li className="group relative flex gap-4 border-b hairline py-4">
      <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-sm text-fg-600 tabular-nums">{rank}</span>
      <div className="min-w-0 flex-1">
        <Link
          href={`/problems/${problem.id}`}
          className="line-clamp-2 text-[15px] leading-snug text-fg-50 [overflow-wrap:anywhere] after:absolute after:inset-0 group-hover:text-signal-300"
        >
          {statement}
        </Link>
        <p className="mt-1.5 flex flex-wrap gap-x-2 text-xs text-fg-500">
          <span className="text-fg-200">{plural(problem.voice_count, "person", "people")}</span>
          <span aria-hidden="true">·</span>
          <span>{problem.platforms.map((p) => platformInfo(p).label).join(", ")}</span>
          <span aria-hidden="true">·</span>
          <span className="text-amber-300/90">{categoryLabel(problem.category)}</span>
          <span aria-hidden="true">·</span>
          <span>{relativeTime(problem.last_seen)}</span>
          {problem.relevance !== null && (
            <>
              <span aria-hidden="true">·</span>
              <span className="text-signal-300">{Math.round(problem.relevance * 100)}% match</span>
            </>
          )}
        </p>
      </div>
      <div className="hidden w-28 shrink-0 flex-col items-end gap-1.5 pt-0.5 sm:flex" title="Demand score">
        <span className="font-mono text-sm text-signal-400 tabular-nums">{problem.demand_score.toFixed(2)}</span>
        <span className="h-1 w-full overflow-hidden rounded-full bg-field-700">
          <span className="block h-full rounded-full bg-signal-500" style={{ width: `${width}%` }} />
        </span>
      </div>
    </li>
  );
}
