import type { Metadata } from "next";
import { ArchitectureDiagram } from "@/components/architecture-diagram";
import { Eyebrow, PageIntro } from "@/components/ui";

export const metadata: Metadata = { title: "How it works" };

const REPO_URL = process.env.XM_REPO_URL ?? "https://github.com/dilipna/xploremore";
const doc = (path: string) => `${REPO_URL}/blob/main/${path}`;

type Measurement = {
  area: string;
  headline: string;
  detail: string;
  caveat?: string;
  report: string;
  reportLabel: string;
};

/**
 * Every number here is copied from a committed report or handoff record that states how to
 * reproduce it. Assistant-made labels are called provisional, as they are in the reports.
 */
const MEASUREMENTS: Measurement[] = [
  {
    area: "Pain-point classifier",
    headline: "P 0.80 · R 0.76 · F1 0.78",
    detail:
      "Logistic regression on bge embeddings + cue features, out-of-fold 5×10 CV with nested C and threshold selection on 485 stratified items. 95% CI: precision 0.72–0.84, recall 0.68–0.81.",
    caveat:
      "Labels are assistant-made (not human-audited). Precision is carried by GitHub issues; on HN/Lobsters/Stack Overflow it is P 0.48 / R 0.39.",
    report: "docs/reports/problem-classifier-v1.md",
    reportLabel: "classifier report",
  },
  {
    area: "Problem clustering",
    headline: "1,553 discussions → 493 problems",
    detail:
      "528 posts admitted as problems, joined across authors under an advisory lock (a race test fails 3/3 with the lock disabled). Merge audit after fixes: 23 of 35 joins correct (65.7%, Wilson CI 49–79%).",
    caveat: "Audited by an assistant on the same corpus the fixes came from, so optimistic. Merge recall is unmeasured.",
    report: "docs/reports/problem-clustering-v1.md",
    reportLabel: "clustering report",
  },
  {
    area: "Story deduplication",
    headline: "MinHash-LSH + dense + logistic pair scorer",
    detail:
      "Candidate generation verified against theory (16×4 bands), a calibrated scorer with a version-conflict feature, and an advisory lock whose race test fails 10/10 without it. Second error audit: 7 of 8 merges correct.",
    caveat: "Pair labels are assistant-made and small (27 positives); metrics are provisional.",
    report: "docs/clustering.md",
    reportLabel: "clustering design",
  },
  {
    area: "Ingest correctness",
    headline: "796 new articles, 45 duplicate no-ops, 0 failures",
    detail:
      "A full live run through poller → Pub/Sub → ingestor → indexer. URL canonicalization is fuzzed (22M runs; the fuzzer found a real host-validation bug). The SSRF guard checks the resolved IP at connect time, defeating DNS rebinding.",
    report: "CONTINUE_SESSION.md",
    reportLabel: "measurement log",
  },
  {
    area: "Rate-limit fail-fast",
    headline: "1,155 deliveries · 0 wasted timeouts",
    detail:
      "The ingestor now refuses a per-host rate-limit slot that would leave no time to fetch, returning it to the limiter instead of burning a 20 s timeout. On a 43-source run: 727 throttled in milliseconds, 25 genuine transient failures.",
    report: "CONTINUE_SESSION.md",
    reportLabel: "measurement log",
  },
  {
    area: "Agent integration A/B",
    headline: "16 live trials · honest confound",
    detail:
      "Pro2Pro's research agent with XploreMore vs its own HN/web search, same model and guardrails. The XploreMore arm shortlisted fewer ideas — but 3 of its 8 trials timed out on an 8k-tokens/min provider tier (0 of 8 baseline), so this measures a token budget, not problem quality.",
    caveat: "Small sample; the report recommends a re-run on a higher-throughput tier before any quality claim.",
    report: "docs/reports/pro2pro-discovery-ab.md",
    reportLabel: "A/B report",
  },
];

const PRINCIPLES = [
  {
    title: "Exactly-once effects on an at-least-once bus",
    body: "Every event carries an idempotency key; the indexer claims it inside the same transaction as its writes, with per-message savepoints. Redelivery is a no-op, not a duplicate.",
  },
  {
    title: "Untrusted fetching is isolated",
    body: "The Go ingestor fetches arbitrary web pages with SSRF protection, robots.txt, per-host rate limits and a size cap after decompression — and has no database credentials at all.",
  },
  {
    title: "Interpretable ranking",
    body: "Demand is a product of five named factors, returned by the API so any agent or person can see why a problem ranks where it does. A learned ranker has to beat it on a judged set first.",
  },
  {
    title: "Agents consume, they don't serve",
    body: "XploreMore has no LLM in its serving path: CPU embeddings, classical IR and a numpy classifier. Agents live in Pro2Pro and reach this system through a versioned API contract and an MCP server.",
  },
];

export default function HowItWorksPage() {
  return (
    <>
      <PageIntro eyebrow="How it works" title="A search and ranking system for real problems.">
        <p className="mt-5 max-w-3xl text-pretty text-lg leading-relaxed text-fg-400">
          News is mostly announcements; problems live in discussions. XploreMore ingests both, deduplicates coverage
          into stories, classifies which discussion posts report a real pain point, clusters them across people and
          platforms, and ranks the result by demand — then serves it to people here and to agents over MCP.
        </p>
      </PageIntro>

      <section className="mx-auto max-w-6xl px-5 py-12">
        <div className="panel overflow-x-auto p-4 md:p-8">
          <div className="min-w-[720px]">
            <ArchitectureDiagram />
          </div>
        </div>
        <p className="mt-3 font-mono text-[11px] text-fg-600">
          Go edge · Python data plane · Postgres 17 + pgvector · Redis · Pub/Sub · Cloud Run · Terraform with keyless
          (OIDC) deploys
        </p>
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-12">
        <Eyebrow>Measured, not claimed</Eyebrow>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight">Every number links to the report that produced it.</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {MEASUREMENTS.map((m) => (
            <article key={m.area} className="panel flex flex-col p-6">
              <p className="font-mono text-[11px] uppercase tracking-wider text-fg-500">{m.area}</p>
              <p className="mt-3 font-mono text-xl text-signal-300">{m.headline}</p>
              <p className="mt-3 text-sm leading-relaxed text-fg-200">{m.detail}</p>
              {m.caveat && <p className="mt-3 text-xs leading-relaxed text-amber-300/90">Caveat: {m.caveat}</p>}
              <a
                href={doc(m.report)}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-auto pt-5 font-mono text-[11px] text-signal-400 hover:text-signal-300"
              >
                {m.reportLabel} ↗
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-16">
        <Eyebrow>Design principles</Eyebrow>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {PRINCIPLES.map((p) => (
            <div key={p.title} className="border-l-2 border-signal-700 pl-5">
              <h3 className="text-[15px] font-semibold text-fg-50">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-fg-400">{p.body}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
