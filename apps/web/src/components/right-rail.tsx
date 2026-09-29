import Link from "next/link";
import { getProblems, getStats } from "@/lib/api";
import { displayStatement, formatCount, platformInfo } from "@/lib/format";

/** Trending problems and live corpus numbers, shown beside the feed. Real data only. */
export async function RightRail({ showProblems = true }: { showProblems?: boolean }) {
  const [problems, stats] = await Promise.all([
    showProblems ? getProblems({ min_voices: 2, limit: 5 }) : Promise.resolve(null),
    getStats(),
  ]);
  const s = stats.data;
  return (
    <div className="flex flex-col gap-4">
      {problems?.data && problems.data.results.length > 0 && (
        <section className="panel overflow-hidden">
          <div className="flex items-baseline justify-between px-4 pt-4">
            <h2 className="text-[15px] font-semibold">Trending problems</h2>
            <Link href="/problems" className="text-xs text-signal-400 hover:text-signal-300">
              See all
            </Link>
          </div>
          <ol className="mt-2">
            {problems.data.results.map((p, i) => (
              <li key={p.id} className="group relative flex gap-3 border-t hairline px-4 py-3 first:border-t-0 hover:bg-field-850">
                <span className="w-4 pt-0.5 font-mono text-sm text-fg-600">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/problems/${p.id}`}
                    className="line-clamp-2 text-sm leading-snug text-fg-50 [overflow-wrap:anywhere] after:absolute after:inset-0 group-hover:text-signal-300"
                  >
                    {displayStatement(
                      p.statement,
                      p.evidence.map((e) => e.excerpt),
                    )}
                  </Link>
                  <p className="mt-1 text-xs text-fg-500">
                    <span className="text-signal-400">{p.voice_count} people</span> ·{" "}
                    {p.platforms.map((x) => platformInfo(x).label).join(", ")}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {s && (
        <section className="panel p-4">
          <h2 className="text-[15px] font-semibold">By the numbers</h2>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
            {(
              [
                [s.sources, "sources"],
                [s.stories, "stories"],
                [s.discussions, "discussions read"],
                [s.voices, "distinct people"],
                [s.problems, "problems (30 days)"],
                [s.multi_voice_problems, "reported by 2+"],
              ] as const
            ).map(([value, label]) => (
              <div key={label}>
                <dt className="font-mono text-lg text-fg-50 tabular-nums">{formatCount(value)}</dt>
                <dd className="text-xs text-fg-500">{label}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <p className="px-1 text-xs leading-relaxed text-fg-600">
        XploreMore · built by Dilip Nallamasa ·{" "}
        <Link href="/how-it-works" className="hover:text-signal-300">
          About
        </Link>
      </p>
    </div>
  );
}
