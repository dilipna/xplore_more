import Link from "next/link";
import { ProblemCard } from "@/components/problem-card";
import { Metric, PageIntro, Unavailable } from "@/components/ui";
import { getProblems, getStats, type ProblemCategory } from "@/lib/api";
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

  const [stats, first] = await Promise.all([
    getStats(),
    getProblems({ topic: topic.length >= 2 ? topic : undefined, category, min_voices: minVoices, limit: 20 }),
  ]);

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

  return (
    <>
      <PageIntro
        eyebrow="Problem intelligence"
        title={
          <>
            What are engineers <span className="text-signal-400">struggling with</span> right now?
          </>
        }
      >
        <p className="mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-fg-400">
          Real pain points mined from Hacker News, GitHub issues, Lobsters and Stack Exchange — classified,
          clustered across people and platforms, and ranked by demand. No LLM in the serving path.
        </p>
        {s && (
          <div className="mt-10 grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6">
            <Metric value={formatCount(s.sources)} label="sources polled" />
            <Metric value={formatCount(s.discussions)} label="discussions read" />
            <Metric value={formatCount(s.voices)} label="distinct people" />
            <Metric value={formatCount(s.problems)} label="problems, last 30 days" />
            <Metric value={formatCount(s.multi_voice_problems)} label="reported by 2+ people" />
            <Metric value={formatCount(s.articles + s.discussions)} label="documents indexed" />
          </div>
        )}
      </PageIntro>

      <section className="mx-auto max-w-6xl px-5 py-10">
        <form action="/" method="get" className="flex flex-col gap-3 md:flex-row">
          {category && <input type="hidden" name="category" value={category} />}
          {minVoices === 1 && <input type="hidden" name="voices" value="1" />}
          <input
            type="search"
            name="topic"
            defaultValue={topic}
            placeholder="Filter by topic — e.g. tool calling, vllm, kubernetes…"
            className="h-12 flex-1 rounded-xl border hairline bg-field-900 px-4 text-[15px] text-fg-50 placeholder:text-fg-600 focus:border-signal-500 focus:outline-none"
            aria-label="Topic"
          />
          <button
            type="submit"
            className="h-12 rounded-xl bg-signal-400 px-6 text-sm font-semibold text-field-950 transition-colors hover:bg-signal-300"
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
