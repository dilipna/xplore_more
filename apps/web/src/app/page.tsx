import Link from "next/link";
import { redirect } from "next/navigation";
import { AutoRefresh } from "@/components/live";
import { TopStories } from "@/components/top-stories";
import { Unavailable } from "@/components/ui";
import { getProblems, getStats, getTopStories } from "@/lib/api";
import { displayStatement, formatCount, plural } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ topic?: string; category?: string; voices?: string }>;

export default async function HomePage({ searchParams }: { searchParams: SearchParams }) {
  // The problem list used to live here; keep old filter links working.
  const sp = await searchParams;
  if (sp.topic || sp.category || sp.voices) {
    const q = new URLSearchParams(Object.entries(sp).filter(([, v]) => v) as [string, string][]);
    redirect(`/problems?${q}`);
  }

  const [top, problems, stats] = await Promise.all([
    getTopStories(),
    getProblems({ min_voices: 2, limit: 6 }),
    getStats(),
  ]);
  const stories = top.data?.results ?? [];
  const s = stats.data;

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-5 py-8 lg:grid-cols-[1fr_320px]">
      <AutoRefresh seconds={60} />
      <section className="min-w-0">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">Top stories</h1>
          <span className="text-xs text-fg-500">last {top.windowHours === 72 ? "3 days" : "24 hours"}</span>
        </div>
        {!top.data ? (
          <Unavailable what="the news" />
        ) : (
          <>
            <TopStories stories={stories} count={12} />
            <Link href="/feed" className="mt-4 inline-block text-sm text-signal-400 hover:text-signal-300">
              More stories →
            </Link>
          </>
        )}
      </section>

      <aside className="flex min-w-0 flex-col gap-6">
        <div className="panel p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-semibold">Most reported problems</h2>
            <Link href="/problems" className="text-xs text-signal-400 hover:text-signal-300">
              See all
            </Link>
          </div>
          {!problems.data ? (
            <p className="mt-3 text-sm text-fg-500">Couldn&apos;t load problems right now.</p>
          ) : (
            <ol className="mt-3">
              {problems.data.results.map((p) => (
                <li key={p.id} className="group relative border-t hairline py-3 first:border-t-0 first:pt-1">
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
                    <span className="text-signal-400">{plural(p.voice_count, "person", "people")}</span> reported this
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>

        {s && (
          <div className="panel p-5">
            <h2 className="text-[15px] font-semibold">By the numbers</h2>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              {[
                [s.sources, "sources"],
                [s.stories, "stories"],
                [s.discussions, "discussions read"],
                [s.voices, "distinct people"],
                [s.problems, "problems (30 days)"],
                [s.multi_voice_problems, "reported by 2+"],
              ].map(([value, label]) => (
                <div key={label}>
                  <dt className="font-mono text-lg text-fg-50 tabular-nums">{formatCount(value as number)}</dt>
                  <dd className="text-xs text-fg-500">{label}</dd>
                </div>
              ))}
            </dl>
            <Link href="/how-it-works" className="mt-4 inline-block text-xs text-signal-400 hover:text-signal-300">
              How this works →
            </Link>
          </div>
        )}
      </aside>
    </div>
  );
}
