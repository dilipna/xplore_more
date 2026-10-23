import type { Metadata } from "next";
import Link from "next/link";
import { SignalMap } from "@/components/signal-map";
import { Unavailable } from "@/components/ui";
import { getMap } from "@/lib/api";
import { recordedMode } from "@/lib/web-mode";

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
            {recordedMode()
              ? "Every dot comes from the dated capture: a story from its seven-day window (green) or a reported problem hypothesis (amber)."
              : "Every dot is a story from the last 7 days (green) or a problem engineers are reporting (amber)."} Dots sit
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
        the titles. Only nearness means anything; the axes don&apos;t. {recordedMode()
          ? "This edition preserves the coordinates from its dated capture."
          : "The layout is recomputed at most every few minutes and is deterministic for the same data."}
      </p>
      {d && (
        <details className="panel mt-5 p-5">
          <summary className="cursor-pointer font-semibold text-fg-50">
            Browse mapped records ({d.points.length})
          </summary>
          <p className="mt-3 text-sm text-fg-400">
            Open the same records using links, without pointing at a map dot.
          </p>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {d.points.map((point) => (
              <li key={`${point.kind}-${point.id}`} className="min-w-0">
                <Link
                  href={`/${point.kind === "story" ? "stories" : "problems"}/${point.id}`}
                  className="block rounded-lg border hairline p-3 text-sm text-fg-200 hover:border-signal-400 hover:text-signal-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal-400 [overflow-wrap:anywhere]"
                >
                  <span className="mb-1 block font-mono text-[10px] uppercase text-fg-500">{point.kind}</span>
                  {point.title}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
