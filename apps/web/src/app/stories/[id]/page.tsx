import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Eyebrow, Metric, Unavailable } from "@/components/ui";
import { getStory } from "@/lib/api";
import { relativeTime, shortDate } from "@/lib/format";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Story" };

export default async function StoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const storyId = Number(id);
  if (!Number.isInteger(storyId) || storyId < 1) notFound();
  const result = await getStory(storyId);
  if (result.status === 404) notFound();
  const d = result.data;

  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <Link href="/search" className="font-mono text-xs text-fg-500 hover:text-fg-50">
        ← search
      </Link>
      {!d ? (
        <div className="mt-8">
          <Unavailable what="this story" />
        </div>
      ) : (
        <>
          <h1 className="mt-6 text-pretty text-2xl leading-snug font-semibold tracking-tight md:text-3xl">
            {d.story.title}
          </h1>
          <div className="mt-8 grid grid-cols-3 gap-6">
            <Metric value={d.story.source_count} label="independent sources" />
            <Metric value={d.story.article_count} label="articles merged" />
            <Metric value={relativeTime(d.story.first_seen_at)} label="first seen" />
          </div>
          <section className="mt-12">
            <Eyebrow>Every article in this story</Eyebrow>
            <p className="mt-3 text-sm leading-relaxed text-fg-400">
              Clustered by MinHash-LSH near-duplicate detection plus dense-embedding candidates, then a logistic pair
              scorer (calibrated prior weights) over embedding similarity, titles, entities, timing and conflicting
              version numbers — so &ldquo;vLLM 0.9&rdquo; and &ldquo;vLLM 0.10&rdquo; never merge.
            </p>
            <ol className="mt-6 flex flex-col gap-3">
              {d.articles.map((a) => (
                <li key={a.id} className="panel flex items-start justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <a
                      href={a.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[15px] text-fg-50 hover:text-signal-300"
                    >
                      {a.title}
                    </a>
                    <p className="mt-1 font-mono text-[11px] text-fg-500">
                      {a.source_name} · {shortDate(a.published_at ?? a.discovered_at)}
                    </p>
                  </div>
                  <span className="shrink-0 font-mono text-[11px] text-fg-600">↗</span>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
