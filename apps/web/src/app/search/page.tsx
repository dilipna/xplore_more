import type { Metadata } from "next";
import Link from "next/link";
import { StoryRow } from "@/components/story-row";
import { Eyebrow, PageIntro, Unavailable } from "@/components/ui";
import { parseServerTiming, search } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Search" };

const SUGGESTED = ["vllm", "claude", "kubernetes", "rag evaluation", "open weights model"];

const STAGE: Record<string, { label: string; what: string }> = {
  embed: { label: "Embed query", what: "bge-small-en-v1.5 on CPU (ONNX), with the BGE query instruction" },
  lexical: { label: "Lexical", what: "Postgres full-text search, top 200" },
  dense: { label: "Dense", what: "pgvector HNSW over halfvec embeddings, top 200" },
  fusion: { label: "Fusion", what: "Reciprocal Rank Fusion (k=60), collapsed to stories" },
  rerank: { label: "Rerank", what: "LightGBM LambdaMART over the fused top 50 (when enabled)" },
  hydrate: { label: "Hydrate", what: "Story titles, sources and counts" },
};
const ORDER = ["embed", "lexical", "dense", "fusion", "rerank", "hydrate"];

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q: raw } = await searchParams;
  const q = (raw ?? "").trim().slice(0, 256);
  const result = q ? await search(q) : null;
  const stages = parseServerTiming(result?.timing ?? null).sort(
    (a, b) => ORDER.indexOf(a.name) - ORDER.indexOf(b.name),
  );
  const serverTotal = stages.reduce((sum, s) => sum + s.ms, 0);
  const maxStage = Math.max(1, ...stages.map((s) => s.ms));

  return (
    <>
      <PageIntro eyebrow="Hybrid search" title="Search the tech news, one story per event.">
        <p className="mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-fg-400">
          Lexical and semantic retrieval fused with Reciprocal Rank Fusion, then collapsed so ten outlets covering one
          release show up as one story.
        </p>
        <form action="/search" method="get" className="mt-8 flex flex-col gap-3 md:flex-row">
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search — try vllm, claude, kubernetes…"
            className="h-12 flex-1 rounded-xl border hairline bg-field-900 px-4 text-[15px] text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:shadow-[0_0_0_3px_rgb(57_255_127/0.15),0_0_24px_-6px_rgb(57_255_127/0.6)] focus:outline-none"
            aria-label="Search query"
            autoFocus={!q}
          />
          <button
            type="submit"
            className="h-12 rounded-xl bg-signal-400 px-6 text-sm font-semibold text-field-950 shadow-[0_0_24px_-6px_rgb(57_255_127/0.8)] transition-all hover:bg-signal-300 hover:shadow-[0_0_32px_-4px_rgb(57_255_127/0.9)]"
          >
            Search
          </button>
        </form>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="mr-1 font-mono text-[11px] uppercase tracking-wider text-fg-600">try</span>
          {SUGGESTED.map((s) => (
            <Link
              key={s}
              href={`/search?q=${encodeURIComponent(s)}`}
              className="rounded-full border hairline px-3 py-1 text-fg-400 transition-colors hover:border-signal-500/50 hover:text-fg-50"
            >
              {s}
            </Link>
          ))}
        </div>
      </PageIntro>

      {result && (
        <section className="mx-auto grid max-w-6xl gap-8 px-5 py-10 lg:grid-cols-[1fr_320px]">
          <div className="min-w-0">
            {!result.data ? (
              <Unavailable what="search results" />
            ) : result.data.results.length === 0 ? (
              <p className="text-fg-400">No stories match “{q}”.</p>
            ) : (
              <>
                <p className="mb-4 text-sm text-fg-400">
                  {result.data.results.length} stories for “{q}”
                  {result.data.degraded.length > 0 && (
                    <span className="text-amber-300"> — degraded: {result.data.degraded.join(", ")}</span>
                  )}
                </p>
                <ol className="flex flex-col gap-3">
                  {result.data.results.map((story, i) => (
                    <StoryRow key={story.id} story={story} rank={i + 1} />
                  ))}
                </ol>
              </>
            )}
          </div>

          {result.data && (
            <aside className="panel h-fit p-5 lg:sticky lg:top-24">
              <Eyebrow>Under the hood</Eyebrow>
              <p className="mt-3 text-xs leading-relaxed text-fg-500">
                Real stage timings from this request&apos;s <span className="font-mono">Server-Timing</span> header.
              </p>
              <div className="mt-5 flex flex-col gap-4">
                {stages.map((s) => (
                  <div key={s.name}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="text-fg-200">{STAGE[s.name]?.label ?? s.name}</span>
                      <span className="font-mono text-xs text-signal-300 tabular-nums">{s.ms.toFixed(1)} ms</span>
                    </div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-field-700">
                      <div
                        className="h-full rounded-full bg-signal-400 shadow-[0_0_10px_rgb(57_255_127/0.7)]"
                        style={{ width: `${Math.max(2, (s.ms / maxStage) * 100)}%` }}
                      />
                    </div>
                    <p className="mt-1 text-[11px] leading-snug text-fg-600">{STAGE[s.name]?.what}</p>
                  </div>
                ))}
              </div>
              <div className="mt-5 border-t hairline pt-4 font-mono text-[11px] leading-relaxed text-fg-500">
                <div className="flex justify-between">
                  <span>server stages</span>
                  <span className="text-fg-200 tabular-nums">{serverTotal.toFixed(1)} ms</span>
                </div>
                <div className="flex justify-between">
                  <span>round trip from this page</span>
                  <span className="text-fg-200 tabular-nums">{Math.round(result.elapsedMs)} ms</span>
                </div>
              </div>
            </aside>
          )}
        </section>
      )}
    </>
  );
}
