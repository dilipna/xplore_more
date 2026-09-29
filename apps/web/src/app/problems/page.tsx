import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/live";
import { ProblemCard } from "@/components/problem-card";
import { PageIntro, Unavailable } from "@/components/ui";
import { getProblems, type ProblemCategory } from "@/lib/api";
import { CATEGORIES, CATEGORY_LABEL } from "@/lib/format";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Problems" };

const POPULAR = ["tool calling", "vllm", "kubernetes", "rag", "gpu memory"];

type SearchParams = Promise<{ topic?: string; category?: string; voices?: string }>;

function href(params: { topic?: string; category?: string; voices?: string }) {
  const q = new URLSearchParams();
  if (params.topic) q.set("topic", params.topic);
  if (params.category) q.set("category", params.category);
  if (params.voices) q.set("voices", params.voices);
  const s = q.toString();
  return s ? `/problems?${s}` : "/problems";
}

const pill = (on: boolean) =>
  `rounded-full px-3 py-1 text-sm transition-colors ${
    on ? "bg-signal-400/10 text-signal-400" : "text-fg-400 hover:text-signal-300"
  }`;

export default async function ProblemsPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const topic = (sp.topic ?? "").trim().slice(0, 256);
  const category = CATEGORIES.includes(sp.category as ProblemCategory) ? (sp.category as ProblemCategory) : undefined;
  const minVoices = sp.voices === "1" ? 1 : 2;
  const query = { topic: topic.length >= 2 ? topic : undefined, category, limit: 25 };

  // A narrow topic often has only one-person reports; show those instead of an empty page.
  let problems = await getProblems({ ...query, min_voices: minVoices });
  let widened = false;
  if (problems.data && problems.data.results.length === 0 && minVoices > 1) {
    problems = await getProblems({ ...query, min_voices: 1 });
    widened = true;
  }
  const results = problems.data?.results ?? [];
  const maxDemand = results.reduce((m, p) => Math.max(m, p.demand_score), 0);

  return (
    <>
      <AutoRefresh seconds={60} />
      <PageIntro title="Problems people keep running into">
        <p className="mt-3 max-w-2xl text-fg-400">
          Posts from Hacker News, GitHub issues, Lobsters and Stack Exchange, grouped when different people describe the
          same problem, and sorted by demand.
        </p>
        <form action="/problems" method="get" className="mt-6 flex max-w-2xl gap-2">
          {category && <input type="hidden" name="category" value={category} />}
          {minVoices === 1 && <input type="hidden" name="voices" value="1" />}
          <input
            type="search"
            name="topic"
            defaultValue={topic}
            placeholder="Filter by topic, e.g. tool calling"
            className="h-11 min-w-0 flex-1 rounded-lg border hairline bg-field-900 px-3 text-[15px] text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:outline-none"
            aria-label="Topic"
          />
          <button
            type="submit"
            className="h-11 rounded-lg bg-signal-400 px-5 text-sm font-semibold text-field-950 hover:bg-signal-300"
          >
            Filter
          </button>
        </form>
        <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-sm text-fg-500">
          Popular:
          {POPULAR.map((t) => (
            <Link key={t} href={href({ topic: t, category, voices: sp.voices })} className="text-fg-200 hover:text-signal-300">
              {t}
            </Link>
          ))}
          {topic && (
            <Link href={href({ category, voices: sp.voices })} className="text-signal-400 hover:text-signal-300">
              clear
            </Link>
          )}
        </p>
      </PageIntro>

      <section className="mx-auto max-w-6xl px-5 pt-5 pb-12">
        <div className="flex flex-wrap items-center gap-1 border-b hairline pb-4">
          <Link href={href({ topic, voices: sp.voices })} className={pill(!category)}>
            All
          </Link>
          {CATEGORIES.map((c) => (
            <Link key={c} href={href({ topic, category: c, voices: sp.voices })} className={pill(category === c)}>
              {CATEGORY_LABEL[c]}
            </Link>
          ))}
          <Link
            href={href({ topic, category, voices: minVoices === 2 ? "1" : undefined })}
            className="ml-auto text-sm text-fg-400 hover:text-signal-300"
          >
            {minVoices === 2 ? "Include one-person reports" : "Only problems 2+ people reported"}
          </Link>
        </div>

        {!problems.data ? (
          <div className="mt-6">
            <Unavailable what="problems" />
          </div>
        ) : results.length === 0 ? (
          <p className="mt-6 text-fg-400">Nothing matches that filter.</p>
        ) : (
          <>
            {(topic || widened) && (
              <p className="mt-4 text-sm text-fg-500">
                {topic && <>Showing problems about &ldquo;{topic}&rdquo;, best match first. </>}
                {widened && <span className="text-amber-300">No problem here has 2+ reports yet, so one-person reports are shown.</span>}
              </p>
            )}
            <ol className="mt-2">
              {results.map((p, i) => (
                <ProblemCard key={p.id} problem={p} rank={i + 1} maxDemand={maxDemand} />
              ))}
            </ol>
          </>
        )}
      </section>
    </>
  );
}
