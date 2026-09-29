import type { Metadata } from "next";
import Link from "next/link";
import { StoryRow } from "@/components/story-row";
import { Eyebrow, PageIntro, Unavailable } from "@/components/ui";
import { parseServerTiming, search } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Search" };

const SUGGESTED = ["vllm", "kubernetes", "rust adoption", "rag evaluation", "open weights model"];

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
      <PageIntro title="Search">
        <p className="mt-3 max-w-2xl text-fg-400">
          Matches words and meaning at the same time, so a question finds the right story even when it uses different
          words. Coverage of the same event comes back as one result.
        </p>
        <form action="/search" method="get" className="mt-6 flex max-w-2xl gap-2">
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Try vllm, kubernetes, rust adoption"
            className="h-11 min-w-0 flex-1 rounded-lg border hairline bg-field-900 px-3 text-[15px] text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:outline-none"
            aria-label="Search query"
            autoFocus={!q}
          />
          <button type="submit" className="h-11 rounded-lg bg-signal-400 px-5 text-sm font-semibold text-field-950 hover:bg-signal-300">
            Search
          </button>
        </form>
        <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-sm text-fg-500">
          Popular:
          {SUGGESTED.map((t) => (
            <Link key={t} href={`/search?q=${encodeURIComponent(t)}`} className="text-fg-200 hover:text-signal-300">
              {t}
            </Link>
          ))}
        </p>
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
                <p className="mb-1 text-sm text-fg-400">
                  {result.data.results.length} results for &ldquo;{q}&rdquo;
                  {result.data.degraded.length > 0 && (
                    <span className="text-amber-300"> (keyword matches only right now)</span>
                  )}
                </p>
                <ol>
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
                How long each step of this search took, from the API&apos;s <span className="font-mono">Server-Timing</span> header.
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
                  <span>total on the server</span>
                  <span className="text-fg-200 tabular-nums">{serverTotal.toFixed(1)} ms</span>
                </div>
                <div className="flex justify-between">
                  <span>round trip</span>
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
