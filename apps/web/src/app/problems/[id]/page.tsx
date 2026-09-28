import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CategoryBadge, Eyebrow, Metric, PlatformBadge, Unavailable } from "@/components/ui";
import { getProblem, type DemandFactors } from "@/lib/api";
import { displayStatement, formatCount, platformInfo, plural, relativeTime, shortDate } from "@/lib/format";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  return { title: `Problem ${id}` };
}

/** Each factor of demand v0, in the order the formula multiplies them (xm_problems/demand.py). */
const FACTORS: { key: keyof DemandFactors; label: string; formula: string; note: string }[] = [
  {
    key: "voices",
    label: "Voices",
    formula: "log(1 + effective voices)",
    note: "Distinct people, each weighted by the classifier's confidence that they reported a problem. One person posting five times counts once.",
  },
  {
    key: "sources",
    label: "Sources",
    formula: "1 + 0.5 · log(1 + sources)",
    note: "Independent corroboration across sources, with diminishing returns.",
  },
  {
    key: "recency",
    label: "Recency",
    formula: "0.5 ^ (days since last seen / 30)",
    note: "30-day half-life from the last sighting: problems people still report stay warm.",
  },
  {
    key: "engagement",
    label: "Engagement",
    formula: "1 + 0.2 · log(1 + points + replies + reactions)",
    note: "A deliberately weak signal, so one viral thread can't outrank many independent voices.",
  },
  {
    key: "category",
    label: "Category prior",
    formula: "hand-set weight",
    note: "Gaps a new product can fill rank slightly above bugs the owning project usually fixes itself.",
  },
];

function engagementText(e: { points: number | null; comments: number | null; reactions: number | null }) {
  const parts = [];
  if (e.points) parts.push(`${formatCount(e.points)} points`);
  if (e.comments) parts.push(`${formatCount(e.comments)} replies`);
  if (e.reactions) parts.push(`${formatCount(e.reactions)} reactions`);
  return parts.join(" · ");
}

export default async function ProblemPage({ params }: { params: Params }) {
  const { id } = await params;
  const problemId = Number(id);
  if (!Number.isInteger(problemId) || problemId < 1) notFound();

  const result = await getProblem(problemId);
  if (result.status === 404) notFound();
  const p = result.data;

  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      <Link href="/" className="font-mono text-xs text-fg-500 hover:text-fg-50">
        ← all problems
      </Link>

      {!p ? (
        <div className="mt-8">
          <Unavailable what="this problem" />
        </div>
      ) : (
        <>
          <header className="mt-6">
            <div className="flex flex-wrap items-center gap-2">
              <CategoryBadge category={p.category} />
              {p.platforms.map((pl) => (
                <PlatformBadge key={pl} platform={pl} />
              ))}
              <span className="font-mono text-[11px] text-fg-600">problem #{p.id}</span>
            </div>
            <h1 className="mt-4 max-w-4xl text-pretty text-2xl leading-snug font-semibold tracking-tight text-fg-50 md:text-3xl">
              {displayStatement(
                p.statement,
                p.evidence.map((e) => e.excerpt),
              )}
            </h1>
            <div className="mt-8 grid grid-cols-2 gap-6 sm:grid-cols-5">
              <Metric value={formatCount(p.voice_count)} label="distinct people" />
              <Metric value={p.effective_voices.toFixed(2)} label="effective voices" />
              <Metric value={formatCount(p.source_count)} label="sources" />
              <Metric value={formatCount(p.member_count)} label="posts clustered" />
              <Metric value={relativeTime(p.last_seen)} label={`first seen ${shortDate(p.first_seen)}`} />
            </div>
          </header>

          <section className="mt-12 grid gap-8 lg:grid-cols-[1.1fr_1fr]">
            <div className="panel p-6">
              <Eyebrow>Why it ranks here</Eyebrow>
              <p className="mt-3 text-sm leading-relaxed text-fg-400">
                Demand is an interpretable product of five factors, recomputed at request time — not a black box.
                Every factor below is what the API actually returned for this problem.
              </p>
              <div className="mt-6 flex flex-col gap-5">
                {FACTORS.map((f) => (
                  <div key={f.key}>
                    <div className="flex items-baseline justify-between gap-4">
                      <span className="text-sm font-medium text-fg-50">{f.label}</span>
                      <span className="font-mono text-sm text-signal-300 tabular-nums">
                        ×{p.demand_factors[f.key].toFixed(3)}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-fg-500">{f.formula}</p>
                    <p className="mt-1 text-xs leading-relaxed text-fg-600">{f.note}</p>
                  </div>
                ))}
                <div className="flex items-baseline justify-between border-t hairline pt-4">
                  <span className="text-sm font-semibold text-fg-50">Demand score</span>
                  <span className="font-mono text-xl text-signal-400 tabular-nums">{p.demand_score.toFixed(3)}</span>
                </div>
                <p className="font-mono text-[11px] text-fg-600">scorer {p.scorer_version}</p>
              </div>
            </div>

            <div>
              <Eyebrow>Evidence — {plural(p.evidence.length, "post")}</Eyebrow>
              <p className="mt-3 text-sm leading-relaxed text-fg-400">
                Public posts clustered into this problem. Authors are stored only as salted hashes; the confidence is
                the pain-point classifier&apos;s probability that the post reports a problem.
              </p>
              <ol className="mt-6 flex flex-col gap-3">
                {p.evidence.map((e) => {
                  const { label, color } = platformInfo(e.platform);
                  return (
                    <li key={e.url} className="panel p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-fg-500">
                        <span className="flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} aria-hidden="true" />
                          {label} · {shortDate(e.date)}
                        </span>
                        {e.p_problem !== null && <span>problem confidence {e.p_problem.toFixed(2)}</span>}
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-fg-200">{e.excerpt}</p>
                      <div className="mt-3 flex items-center justify-between gap-3 font-mono text-[11px]">
                        <span className="text-fg-600">{engagementText(e.engagement)}</span>
                        <a
                          href={e.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-signal-400 hover:text-signal-300"
                        >
                          open original ↗
                        </a>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
