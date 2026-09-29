import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/live";
import { ProblemCard } from "@/components/problem-card";
import { RightRail } from "@/components/right-rail";
import { Shell } from "@/components/shell";
import { Unavailable } from "@/components/ui";
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
  `rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors ${
    on ? "bg-signal-400 text-black" : "text-fg-400 hover:bg-field-850 hover:text-fg-50"
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

  return (
    <Shell rail={<RightRail showProblems={false} />}>
      <AutoRefresh seconds={60} />
      <section className="panel p-5">
        <h1 className="text-2xl font-bold tracking-tight">Problems people keep running into</h1>
        <p className="mt-1.5 text-sm text-fg-400">
          Posts from Hacker News, GitHub issues, Lobsters and Stack Exchange, grouped when different people describe the
          same problem. The number on the left is how many people reported it.
        </p>
        <form action="/problems" method="get" className="mt-4 flex gap-2">
          {category && <input type="hidden" name="category" value={category} />}
          {minVoices === 1 && <input type="hidden" name="voices" value="1" />}
          <input
            type="search"
            name="topic"
            defaultValue={topic}
            placeholder="Filter by topic, e.g. tool calling"
            className="h-10 min-w-0 flex-1 rounded-full border hairline bg-field-950 px-4 text-sm text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:outline-none"
            aria-label="Topic"
          />
          <button type="submit" className="h-10 rounded-full bg-signal-400 px-5 text-sm font-semibold text-black hover:bg-signal-300">
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
      </section>

      <div className="mt-4 flex flex-wrap items-center gap-1">
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
          {minVoices === 2 ? "Include one-person reports" : "Only 2+ people"}
        </Link>
      </div>

      {!problems.data ? (
        <div className="mt-4">
          <Unavailable what="problems" />
        </div>
      ) : results.length === 0 ? (
        <p className="mt-6 text-fg-400">Nothing matches that filter.</p>
      ) : (
        <>
          {(topic || widened) && (
            <p className="mt-3 text-sm text-fg-500">
              {topic && <>Problems about &ldquo;{topic}&rdquo;, best match first. </>}
              {widened && <span className="text-amber-300">None has 2+ reports yet, so one-person reports are shown.</span>}
            </p>
          )}
          <div className="mt-3 flex flex-col gap-3">
            {results.map((p) => (
              <ProblemCard key={p.id} problem={p} />
            ))}
          </div>
        </>
      )}
    </Shell>
  );
}
