import Link from "next/link";
import { snapshot } from "@/lib/recorded-api";
import manifest from "@/data/demo-snapshot.manifest.json";
export const metadata = { title: "Data, provenance & operating modes" };
const notes = [
  [
    "What is real here?",
    "Source URLs, publication dates and report excerpts come from a bounded public-source collection through the Go poller, local Pub/Sub emulator, Go ingestor, CPU indexer and Postgres. The map uses captured embedding-derived coordinates. Original dates are retained.",
  ],
  [
    "What remains provisional?",
    "Problem labels are model outputs, not independently verified customer demand. Similarity and clustering can be wrong. Reporter counts do not establish willingness to pay. Opening an old report does not establish that it remains unresolved.",
  ],
  [
    "How does this edition work?",
    "Search matches keywords in captured titles. Ranking sliders reuse captured, rounded signals and change the ordering of this packaged subset. Live Postgres/pgvector hybrid retrieval requires the local backend. No source polling or embedding model runs on this public website.",
  ],
  [
    "What do the counts mean?",
    "Source registry size, indexed document counts and packaged story counts describe different things. This edition includes a bounded subset of the local corpus. The data represents one capture, not continuously verified coverage.",
  ],
];
export default function CapturePage() {
  return (
    <div className="mx-auto max-w-5xl px-5 py-12">
      <p className="font-mono text-xs uppercase tracking-[.2em] text-amber-300">
        Evidence / capture notes
      </p>
      <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-6xl">
        Know what you’re
        <br />
        <span className="text-signal-300">looking at.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-base leading-relaxed text-fg-200">
        A dated, working capture of the real local pipeline. Inspect sources,
        search titles, change ranking weights, explore the semantic map and
        export a bounded product brief.
      </p>
      <dl className="my-10 grid gap-px overflow-hidden rounded-2xl border hairline bg-field-600 sm:grid-cols-3">
        {[
          ["Captured (UTC)", new Date(snapshot.captured_at).toUTCString()],
          [
            "Stories in this edition",
            `${snapshot.coverage.exported_stories} of ${snapshot.coverage.corpus_stories} local corpus stories`,
          ],
          [
            "Problem hypotheses",
            `${snapshot.coverage.exported_problems} · machine classified`,
          ],
        ].map(([k, v]) => (
          <div key={k} className="bg-field-900 p-6">
            <dt className="text-xs text-fg-400">{k}</dt>
            <dd className="mt-3 font-mono text-sm text-signal-300">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-6 md:grid-cols-2">
        {notes.map(([title, body]) => (
          <section key={title} className="panel p-7">
            <h2 className="text-xl font-semibold">{title}</h2>
            <p className="mt-4 text-sm leading-relaxed text-fg-200">{body}</p>
          </section>
        ))}
      </div>
      <section className="panel mt-6 p-7">
        <h2 className="text-xl font-semibold">Inspect the evidence</h2>
        <p className="mt-4 break-all font-mono text-xs leading-relaxed text-fg-400">
          Snapshot SHA-256: {manifest.snapshot_sha256}
        </p>
        <div className="mt-6 flex flex-wrap gap-4">
          <a
            href="/api/capture"
            download="xploremore-capture.json"
            className="rounded-full bg-signal-400 px-5 py-2.5 text-sm font-semibold text-black"
          >
            Download capture JSON ↓
          </a>
          <a
            href="https://github.com/dilipna/xplore_more"
            className="rounded-full border hairline px-5 py-2.5 text-sm"
          >
            Source & local setup ↗
          </a>
          <Link
            href="/how-it-works"
            className="rounded-full border hairline px-5 py-2.5 text-sm"
          >
            Architecture & measurements →
          </Link>
        </div>
        <p className="mt-5 text-xs leading-relaxed text-fg-500">
          No credentials, author hashes, full article bodies or embedding
          weights are included. Brief export is a draft for human review; it
          does not authorize a build.
        </p>
      </section>
      <div className="mt-8 flex flex-wrap gap-6 text-sm text-signal-300">
        <Link href="/feed">Explore the feed →</Link>
        <Link href="/problems">Inspect problems →</Link>
        <Link href="/workbench">Draft a brief →</Link>
      </div>
    </div>
  );
}
