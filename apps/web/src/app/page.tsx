import Link from "next/link";
import { ProblemCard } from "@/components/problem-card";
import { AutoRefresh, CountUp } from "@/components/live";
import { TopStories } from "@/components/top-stories";
import { Eyebrow, PageIntro, Unavailable } from "@/components/ui";
import { getProblems, getStats, getTopStories, type ProblemCategory } from "@/lib/api";
import { CATEGORIES, CATEGORY_LABEL, formatCount } from "@/lib/format";

export const dynamic = "force-dynamic";

const SUGGESTED_TOPICS = ["tool calling", "vllm", "kubernetes", "rag", "gpu memory"];

type SearchParams = Promise<{ topic?: string; category?: string; voices?: string }>;

function href(params: { topic?: string; category?: string; voices?: string }) {
  const q = new URLSearchParams();
  if (params.topic) q.set("topic", params.topic);
  if (params.category) q.set("category", params.category);
  if (params.voices) q.set("voices", params.voices);
  const s = q.toString();
  return s ? `/?${s}` : "/";
}

export default async function ProblemsPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const topic = (sp.topic ?? "").trim().slice(0, 256);
  const category = CATEGORIES.includes(sp.category as ProblemCategory) ? (sp.category as ProblemCategory) : undefined;
  const minVoices = sp.voices === "1" ? 1 : 2;

  const [stats, first, topStories] = await Promise.all([
    getStats(),
    getProblems({ topic: topic.length >= 2 ? topic : undefined, category, min_voices: minVoices, limit: 20 }),
    getTopStories(),
  ]);
  const topWindow = topStories.windowHours === 72 ? "3 days" : "24 hours";

  // A narrow topic often has only single-voice problems; say so instead of showing nothing.
  let problems = first;
  let widened = false;
  if (first.data && first.data.results.length === 0 && minVoices > 1) {
    problems = await getProblems({ topic: topic.length >= 2 ? topic : undefined, category, min_voices: 1, limit: 20 });
    widened = true;
  }

  const results = problems.data?.results ?? [];
  const maxDemand = results.reduce((m, p) => Math.max(m, p.demand_score), 0);
  const s = stats.data;

  const top = topStories.data?.results ?? [];
  const tiles = s
    ? [
        { value: s.sources, label: "sources polled" },
        { value: s.discussions, label: "discussions read" },
        { value: s.voices, label: "distinct people" },
        { value: s.problems, label: "problems, last 30 days" },
        { value: s.multi_voice_problems, label: "reported by 2+ people" },
        { value: s.articles + s.discussions, label: "documents indexed" },
      ]
    : [];

  return (
    <>
      <PageIntro
        eyebrow="Live · problem & tech intelligence"
        title={
          <>
            What are engineers <span className="neon-text">struggling with</span> right now?
          </>
        }
      >
        <p className="mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-fg-400">
          Real pain points mined from Hacker News, GitHub issues, Lobsters and Stack Exchange — classified,
          clustered across people and platforms, and ranked by demand. No LLM in the serving path.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3 font-mono text-xs text-fg-400">
          {s && (
            <p className="min-w-0 [overflow-wrap:anywhere]">
              <span className="text-signal-400">&gt;</span> streaming {formatCount(s.sources)} sources ·{" "}
              {formatCount(s.stories)} stories · ranked on CPU
              <span className="cursor-blink ml-0.5 inline-block h-3.5 w-2 translate-y-0.5 bg-signal-400" aria-hidden="true" />
            </p>
          )}
          <span className="text-fg-500">
            <AutoRefresh seconds={60} />
          </span>
        </div>
        {s && (
          <div className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-xl border hairline bg-signal-400/10 sm:grid-cols-3 lg:grid-cols-6">
            {tiles.map((t) => (
              <div key={t.label} className="bg-field-950/90 px-4 py-4">
                <p className="font-mono text-2xl leading-none text-fg-50 md:text-[28px]">
                  <CountUp value={t.value} />
                </p>
                <p className="mt-2 text-[11px] text-fg-500">{t.label}</p>
              </div>
            ))}
          </div>
        )}
      </PageIntro>

      {top.length > 0 && (
        <section className="mx-auto max-w-6xl px-5 pt-12">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <Eyebrow>Top stories right now</Eyebrow>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">What happened in tech, one story per event.</h2>
            </div>
            <p className="font-mono text-[11px] text-fg-600">
              ranker {topStories.data?.ranker} · duplicates across sources collapsed
            </p>
          </div>
          <TopStories stories={top} windowLabel={topWindow} />
        </section>
      )}

      <section className="mx-auto max-w-6xl px-5 pt-14">
        <Eyebrow>Most-demanded problems</Eyebrow>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">Pain points reported by real people, ranked by demand.</h2>
      </section>

      <section className="mx-auto max-w-6xl px-5 pt-6 pb-10">
        <form action="/" method="get" className="flex flex-col gap-3 md:flex-row">
          {category && <input type="hidden" name="category" value={category} />}
          {minVoices === 1 && <input type="hidden" name="voices" value="1" />}
          <input
            type="search"
            name="topic"
            defaultValue={topic}
            placeholder="Filter by topic — e.g. tool calling, vllm, kubernetes…"
            className="h-12 flex-1 rounded-xl border hairline bg-field-900 px-4 text-[15px] text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:shadow-[0_0_0_3px_rgb(57_255_127/0.15),0_0_24px_-6px_rgb(57_255_127/0.6)] focus:outline-none"
            aria-label="Topic"
          />
          <button
            type="submit"
            className="h-12 rounded-xl bg-signal-400 px-6 text-sm font-semibold text-field-950 shadow-[0_0_24px_-6px_rgb(57_255_127/0.8)] transition-all hover:bg-signal-300 hover:shadow-[0_0_32px_-4px_rgb(57_255_127/0.9)]"
          >
            Find problems
          </button>
        </form>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="mr-1 font-mono text-[11px] uppercase tracking-wider text-fg-600">try</span>
          {SUGGESTED_TOPICS.map((t) => (
            <Link
              key={t}
              href={href({ topic: t, category, voices: sp.voices })}
              className="rounded-full border hairline px-3 py-1 text-fg-400 transition-colors hover:border-signal-500/50 hover:text-fg-50"
            >
              {t}
            </Link>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-2 border-t hairline pt-6 text-sm">
          <Link
            href={href({ topic, voices: sp.voices })}
            className={`rounded-lg px-3 py-1.5 ${!category ? "bg-field-800 text-fg-50" : "text-fg-400 hover:text-fg-50"}`}
          >
            All categories
          </Link>
          {CATEGORIES.map((c) => (
            <Link
              key={c}
              href={href({ topic, category: c, voices: sp.voices })}
              className={`rounded-lg px-3 py-1.5 ${category === c ? "bg-field-800 text-fg-50" : "text-fg-400 hover:text-fg-50"}`}
            >
              {CATEGORY_LABEL[c]}
            </Link>
          ))}
          <span className="mx-2 h-5 w-px bg-field-700" aria-hidden="true" />
          <Link
            href={href({ topic, category, voices: minVoices === 2 ? "1" : undefined })}
            className="rounded-lg px-3 py-1.5 text-fg-400 hover:text-fg-50"
          >
            {minVoices === 2 ? "Showing 2+ voices · include single-voice" : "Including single-voice · show 2+ only"}
          </Link>
        </div>

        <div className="mt-8">
          {!problems.data ? (
            <Unavailable what="problems" />
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
                <p className="text-sm text-fg-400">
                  {results.length === 0
                    ? "No problems match."
                    : topic
                      ? `Problems about “${topic}”, ranked by relevance × √demand`
                      : "Ranked by demand: distinct voices, sources, recency and engagement"}
                  {widened && results.length > 0 && (
                    <span className="text-amber-300"> — no multi-voice match, showing single-voice problems</span>
                  )}
                </p>
                <p className="font-mono text-[11px] text-fg-600">
                  ranker {problems.data.ranker} · {Math.round(problems.elapsedMs)} ms
                  {problems.cache ? ` · cache ${problems.cache}` : ""}
                </p>
              </div>
              <div className="flex flex-col gap-3">
                {results.map((p, i) => (
                  <ProblemCard key={p.id} problem={p} rank={i + 1} maxDemand={maxDemand} />
                ))}
              </div>
            </>
          )}
        </div>
      </section>
    </>
  );
}
