import type { Metadata } from "next";
import { SignalMap } from "@/components/signal-map";
import { Unavailable } from "@/components/ui";
import { getMap } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Signal map",
  description: "This week's stories and the problems engineers report, laid out by meaning.",
};

export default async function MapPage() {
  const result = await getMap();
  const d = result.data;
  const stories = d?.points.filter((p) => p.kind === "story").length ?? 0;
  const problems = (d?.points.length ?? 0) - stories;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight">
            Signal <span className="neon-text text-signal-400">map</span>
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-fg-400">
            Every dot is a story from the last 7 days (green) or a problem engineers are reporting (amber). Dots sit
            close together when their text means similar things. The islands are labelled with their most distinctive
            title words, so every label is a word taken from the titles, not generated.
          </p>
        </div>
        {d && (
          <dl className="flex gap-6 font-mono text-xs">
            <div>
              <dt className="text-fg-500">stories</dt>
              <dd className="text-lg text-signal-400">{stories}</dd>
            </div>
            <div>
              <dt className="text-fg-500">problems</dt>
              <dd className="text-lg text-amber-300">{problems}</dd>
            </div>
            <div>
              <dt className="text-fg-500">islands</dt>
              <dd className="text-lg text-fg-50">{d.islands.length}</dd>
            </div>
          </dl>
        )}
      </div>
      {!d ? (
        <div className="mt-6">
          <Unavailable what="the map" />
        </div>
      ) : (
        <SignalMap
          points={d.points}
          islands={d.islands}
          className="panel mt-5 h-[calc(100vh-230px)] min-h-[440px] bg-[radial-gradient(ellipse_at_center,rgb(10_40_22/0.55),transparent_70%)]"
        />
      )}
      <p className="mt-3 text-xs leading-relaxed text-fg-600">
        How it&apos;s made: each story&apos;s lead article and each problem&apos;s centroid is a bge-small-en-v1.5 embedding.
        The server lays them out with t-SNE and groups the layout with k-means; labels use class-based TF-IDF over
        the titles. Only nearness means anything; the axes don&apos;t. It&apos;s recomputed at most every few minutes and
        is deterministic for the same data.
      </p>
    </div>
  );
}
